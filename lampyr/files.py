# -*- coding: utf-8 -*-
"""
Created on Thu Sep 18 11:48:06 2025

@author: mm4114
"""


import h5py
import os
import numpy as np
import pickle
import json
import glob
from dataclasses import is_dataclass, asdict
from lampyr.primatives import Session, Mouse
from lampyr.config import Config
import shutil
import csv
import time
import hashlib

from typing import Union, List


def savejson(fp, data, saveasis=True):
    if not saveasis:
        if is_dataclass(data):
            data = asdict(data)
    with open(fp, 'w') as f:
        json.dump(data, f, indent=2)
    return fp


def loadjson(fp):
    with open(fp, 'r') as f:
        return json.load(f)


def savecsv(fp, data: List[dict]):
    all_keys = []
    for entry in data:
        for key in entry.keys():
            if key not in all_keys:
                all_keys.append(key)

    with open(fp, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(data)
        
def loadcsv(fp):
    data = []
    with open(fp, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data


def savepickle(fp, data):
    with open(fp, 'wb') as f:
        pickle.dump(data, f)
    return fp


def loadpickle(filepath):
    with open(filepath, 'rb') as f:
        data = pickle.load(f)
    return data


def loadh5(fp):
    def recursive_load(h5group):
        # Get the type hint saved by saveh5
        node_type = h5group.attrs.get('_type')
        if node_type == 'ndarray':
            return h5group['array'][()]
        elif node_type == 'scalar' or node_type == 'unknown_fallback_str':
            val = h5group.attrs['value']
            original_py_type = h5group.attrs.get('_original_py_type')

            # Attempt to convert back to original Python type
            if original_py_type == 'int':
                return int(val)
            elif original_py_type == 'float':
                return float(val)
            elif original_py_type == 'bool':
                # Handle boolean string conversion carefully
                if isinstance(val, str):
                    return val.lower() == 'true'
                return bool(val)  # For actual boolean values saved directly
            # Add more types if needed (e.g., complex, bytes)
            # elif original_py_type == 'str_fallback': # This means it was an unhandled type saved as string
            #     # You might want to log a warning here
            #     pass
            return val  # Default for string or if type conversion not handled

        elif node_type == 'dict':
            keys = list(h5group.keys())
            return {k: recursive_load(h5group[k]) for k in keys}
        elif node_type == 'list':  # List or tuple, using the explicit flag
            keys = list(h5group.keys())
            indices = sorted(int(k) for k in keys)
            # Ensure it's a contiguous list of indices for true list reconstruction
            if len(indices) == len(keys) and all(idx == i for i, idx in enumerate(indices)):
                return [recursive_load(h5group[str(i)]) for i in indices]
            else:
                # Fallback to dict if keys are not contiguous for a list
                print(f"Warning: List expected for group '{
                      h5group.name}', but keys are not contiguous. Loading as dictionary.")
                return {k: recursive_load(h5group[k]) for k in keys}
        else:
            # Fallback for old files or unexpected structures
            # If no '_type' attribute, try to guess based on existing children/attributes
            if 'array' in h5group:
                return h5group['array'][()]
            elif 'value' in h5group.attrs:
                return h5group.attrs['value']
            # Assume it's a group that might be a dict or list (try dict first for safety)
            else:
                keys = list(h5group.keys())
                # Try to guess if it's a list by checking if all keys are integer strings
                try:
                    parsed_keys = sorted(int(k) for k in keys)
                    if len(parsed_keys) > 0 and all(pk == i for i, pk in enumerate(parsed_keys)):
                        return [recursive_load(h5group[str(i)]) for i in parsed_keys]
                    else:
                        return {k: recursive_load(h5group[k]) for k in keys}
                except ValueError:  # Not all keys are integers, so definitely a dict
                    return {k: recursive_load(h5group[k]) for k in keys}

    with h5py.File(fp, mode='r') as file:
        if 'root' in file:
            return recursive_load(file['root'])
        else:
            print(f"Warning: 'root' group not found in HDF5 file: {
                  fp}. Returning None.")
            return None  # Or raise an error


def saveh5(fp, data):
    def recursive_save(obj, h5group):
        if isinstance(obj, dict):
            h5group.attrs['_type'] = 'dict'  # Indicate it's a dictionary
            for k, v in obj.items():
                grp = h5group.create_group(str(k))
                recursive_save(v, grp)
        elif isinstance(obj, (list, tuple)):
            h5group.attrs['_type'] = 'list'  # Indicate it's a list/tuple
            for i, v in enumerate(obj):
                grp = h5group.create_group(str(i))
                recursive_save(v, grp)
        elif isinstance(obj, np.ndarray):
            h5group.attrs['_type'] = 'ndarray'  # Indicate it's an ndarray
            h5group.create_dataset('array', data=obj)
        # Added bool for explicit type saving
        elif isinstance(obj, (int, float, str, bool, np.number)):
            h5group.attrs['_type'] = 'scalar'
            h5group.attrs['value'] = obj
            # Store original Python type name for better reconstruction
            h5group.attrs['_original_py_type'] = type(obj).__name__
        else:
            # Fallback for unhandled types (e.g., set, complex, custom objects)
            # Save as string, mark as fallback
            h5group.attrs['_type'] = 'unknown_fallback_str'
            h5group.attrs['value'] = str(obj)
            h5group.attrs['_original_py_type'] = 'str_fallback'

    if is_dataclass(data):
        data = asdict(data)

    with h5py.File(fp, mode='w') as file:
        # Changed to pass data first
        recursive_save(data, file.create_group("root"))

    return fp


def savesessionfile(session: Session,
                    dir_fp: Union[str, os.PathLike] = os.getcwd()
                    ) -> List[os.PathLike]:
    """
    Save a Session object in Lampyr format within a specific directory.

    This function saves two files:
    - A `.lampyr.h5` file containing rig data in HDF5 format.
    - A `.lampyr.json` file containing the rest of the session metadata.

    Parameters
    ----------
    session : Session
        Lampyr Session object to save.
    dir_fp : Union[str, os.PathLike], optional
        Directory in which to save session files. Defaults to current working directory.

    Returns
    -------
    fps : List[os.PathLike]
        List of file paths to the saved files (HDF5 and JSON).
    """
    os.makedirs(dir_fp, exist_ok=True)
    rigdata = session.rigdata
    np_rigdata = {}
    fps = []
    if rigdata is not None:
        for reporttype, reports in rigdata.items():
            np_rigdata[reporttype] = {}
            for datalabel, data in reports.items():
                np_rigdata[reporttype][datalabel] = np.asarray(data)
        fp = saveh5(os.path.join(dir_fp, f'{session.uniquesessionid}.lampyr.h5'),
                    np_rigdata)
        if fp is not None:
            fps.append(fp)
    data = asdict(session)
    data['rigdata'] = None
    fp = savejson(os.path.join(dir_fp, f'{session.uniquesessionid}.lampyr.json'),
                  data)
    if fp is not None:
        fps.append(fp)
    return fps


def loadsessionfile(sessionid: str,
                    dir_fp: Union[str, os.PathLike] = os.getcwd()
                    ) -> Session:
    """
    Load a Lampyr session object from saved HDF5 and JSON files.

    This function reconstructs a Session object using the `.lampyr.h5` and
    `.lampyr.json` files stored in the specified directory. The rig data is
    loaded from the HDF5 file, and all other attributes are restored from
    the JSON file.

    Parameters
    ----------
    sessionid : str
        The unique session ID corresponding to the saved session files.
    dir_fp : Union[str, os.PathLike], optional
        Directory where the session files are located. Defaults to current working directory.

    Raises
    ------
    FileExistsError
        If the directory or required session files do not exist.

    Returns
    -------
    Session
        A reconstructed Lampyr Session object.
    """
    # Check if dir_fp exists
    if not os.path.exists(dir_fp):
        raise FileExistsError(f'{dir_fp} does not exist')

    # Determine the h5 and json filepaths
    h5file = os.path.join(dir_fp,
                          f'{sessionid}.lampyr.h5')
    jsonfile = os.path.join(dir_fp,
                            f'{sessionid}.lampyr.json')

    # Check if the h5 and json files exist
    if not os.path.exists(h5file) or not os.path.exists(jsonfile):
        raise FileExistsError(f'Session is invalid or does not exist. {
                              h5file} or {jsonfile} not found.')

    # Load all data and input into a session object, saves the endtime last
    # to avoid premature locking of session data
    session = Session(rigdata=loadh5(h5file))
    jsonobj = loadjson(jsonfile)
    for index, value in jsonobj.items():
        if index not in ['endtime', 'rigdata']:
            session.__setattr__(index, value)
    session.endtime = jsonobj['endtime']
    return session


def savemousefile(mouse: Mouse,
                  dir_fp: Union[str, os.PathLike] = os.getcwd()
                  ) -> List[os.PathLike]:
    """
    Save a Mouse object in Lampyr format within a specific directory.

    This function saves two files:
    - A `.lampyr.json` file containing mouse metadata.
    - A `.lampyr.csv` file containing mouse session history (if available).

    Parameters
    ----------
    mouse : Mouse
        A Lampyr Mouse object to be saved. Contains metadata and session history.
    dir_fp : Union[str, os.PathLike], optional
        The directory in which to save the mouse files. Defaults to the current working directory.

    Returns
    -------
    List[os.PathLike]
        A list of file paths to the saved files (JSON and optionally CSV).
    """
    os.makedirs(dir_fp, exist_ok=True)

    mouse_json_fp = os.path.join(dir_fp, f'{mouse.mouseid}_mouse.lampyr.json')
    mouse_csv_fp = os.path.join(dir_fp, f'{mouse.mouseid}_history.lampyr.csv')

    mouse_metadata = asdict(mouse)
    mouse_history = mouse_metadata.pop('history', None)

    savejson(mouse_json_fp, mouse_metadata)

    if mouse.mouseid == 'UNKNOWN_MOUSE' or mouse_history is None:
        return [mouse_json_fp]

    savecsv(mouse_csv_fp, mouse_history)

    return [mouse_json_fp, mouse_csv_fp]


def loadmousefile(mouseid: str,
                  dir_fp: Union[str, os.PathLike] = os.getcwd()
                  ) -> Mouse:
    """
    Load a Lampyr Mouse object from saved JSON and CSV files.

    This function reconstructs a Mouse object using:
    - A `.lampyr.json` file containing mouse metadata.
    - A `.lampyr.csv` file containing mouse session history (if available).

    Parameters
    ----------
    mouseid : str
        The unique mouse ID corresponding to the saved files.
    dir_fp : Union[str, os.PathLike], optional
        Directory where the mouse files are stored. Defaults to the current working directory.

    Raises
    ------
    FileExistsError
        If the required JSON file does not exist in the specified directory.

    Returns
    -------
    Mouse
        A reconstructed Mouse object with metadata and optional session history.
    """
    if mouseid == 'UNKNOWN_MOUSE':
        return Mouse(mouseid=mouseid)
    
    mouse_json_fp = os.path.join(dir_fp, f'{mouseid}_mouse.lampyr.json')
    mouse_csv_fp = os.path.join(dir_fp, f'{mouseid}_history.lampyr.csv')
    
    if not os.path.exists(mouse_json_fp):
        raise FileExistsError(f'{mouse_json_fp} does not exist')
    
    mouse_data = loadjson(mouse_json_fp)
    
    if os.path.exists(mouse_csv_fp):
        mouse_data['history'] = loadcsv(mouse_csv_fp)
    
    return Mouse(**mouse_data)
