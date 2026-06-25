# -*- coding: utf-8 -*-
"""
Created on Tue Jun 23 12:52:15 2026

@author: mm4114
"""

from lampyr.rigs.abstract import AbstractInterface, InterfaceData
import threading
import time


class SerialInterface_ArduinoTRV(AbstractInterface):
    def setup(self, baud=115200, timeout=1):
        self.baud = baud
        self.timeout = timeout
        self._find_device()
        self.data = InterfaceData(
            ['arduino_time', 'unix_time', 'report_value'])
        self.abort_flag = False

    def _find_device(self):
        from serial.tools import list_ports
        import serial
        """
        Scan COM ports for an Arduino and open the first one found.

        Raises
        ------
        RuntimeError
            If no Arduino is found in the list of available serial ports.
        """
        ports = list_ports.comports()
        ports = [p for p in ports if 'Arduino' in p.description]
        if not ports:
            raise RuntimeError(
                'No Arduino device found. Check USB connection.')
        port = ports[0]
        self.ser = serial.Serial(port.device, self.baud, timeout=self.timeout)
        time.sleep(2)
        self.ser.reset_input_buffer()
        self.ser.flush()

    def start(self):
        thread = threading.Thread(target=self.listen, daemon=True)
        thread.start()
        time.sleep(2)

    def listen(self):
        """
        Background thread target: continuously read from the serial port.

        Resets the input buffer, then loops calling :meth:`_readserial` until
        the abort flag is set.  Resets the abort flag on exit.
        """
        time.sleep(1)
        self.ser.reset_input_buffer()
        self.ser.flush()
        while not self.abort_flag:
            try:
                self._readserial()
            except Exception as error:
                print(f'WARNING! Unknown serial read error occurred. {error}')
            time.sleep(0.001)

        self.abort_flag = False

    def _readserial(self):
        """
        Drain the serial buffer and store all valid incoming lines.

        Parses each line as ``arduino_timestamp<TAB>event_type<TAB>value``.
        Malformed lines and unicode errors are printed as warnings.  All
        successfully parsed entries are logged into the interface data object.

        Returns
        -------
        list of tuple
            Newly parsed ``(unix_time, [arduino_time, event_type, value])``
            entries from this read cycle.
        """
        responses = []
        while self.ser.in_waiting > 0:
            try:
                response = self.ser.readline().decode().strip()
            except UnicodeDecodeError as error:
                print(error)
                print(
                    'WARNING: UnicodeDecodeError detected. If this reoccurs, restart your script!!!!')
                break
            response = response.split('\t')
            # print(response)
            if len(response) == 3:
                try:
                    timestamp = int(response[0])
                    event_type = str(response[1])
                    value = int(response[2])
                    responses.append(
                        (time.time(), [timestamp, event_type, value]))
                except ValueError as e:
                    print(f"ValueError processing data: {response} - {e}")
            else:
                print(f"Received unexpected data format: {response}")
        for unix_time, (arduino_time, report_type, report_value) in responses:
            self.data.log_report(report_type, arduino_time=arduino_time,
                                 unix_time=unix_time,
                                 report_value=report_value
                                 )
        return responses

    def send_command(self, cmd):
        cmdent = f'{cmd}\n'
        self.ser.write(cmdent.encode())

    def stop(self):
        self.abort_flag = True
        time.sleep(2)
        self.ser.close()

    def dump(self):
        return {'COM PORT': self.ser.port,
                'BAUD': self.ser.baudrate,
                'BYTESIZE': self.ser.bytesize}

class CameraInterface_Arducam(AbstractInterface):
    def setup(self, 
              camera_index = 0,
              tempfiletarget = None,
              playback_framerate = 20,
              check_cooldown_ms = 10
              ):
        #settings
        self.camera_index = camera_index
        self.tempfiletarget = tempfiletarget or 'vid.avi'
        self.fps = playback_framerate
        self.check_cooldown_ms
        
        self.data = InterfaceData(report_values = ['unix_time','frame_num'],
                                  report_types = ['cam_frame_times'])
        
        # Threading/Runtime
        self.lock = threading.Lock()
        self.abort_flag = False
        self.thread = None
        self.frame_idx = 0
        self.current_frame = None
        
        # set during startup
        self.cap = None
        self.out = None
    
    def start(self):
        import cv2
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError("Could not open Camera.")
        self.cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self.out = cv2.VideoWriter(self.tempfiletarget,
                                   fourcc, self.fps,
                                   (width, height),
                                   isColor=False)
        if not self.out.isOpened():
            self.cap.release()
            raise RuntimeError("Could not open VideoWriter.")
        
        self.thread = threading.Thread(target=self._listen, )
    
    def _listen(self):
        while not self.abort_flag:
            ret, frame = self.cap.read()
            
            time.sleep()


if __name__ == '__main__':
    interface = SerialInterface_ArduinoTRV()
    interface.start()
    time.sleep(5)
    interface.stop()
    print(interface.data.reports)
