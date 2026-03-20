@echo off

call conda activate
call conda activate mx_hardware
echo Updating conda environment from mx_hardware.yaml...
call conda env update --name mx_hardware --file "N:\Maxwell\Lampyr\mx_hardware.yaml" --prune
pip install art
pip uninstall lampyr -y
pip install --no-deps "git+https://github.com/mxwllmadden/Lampyr.git@main"
cmd /k