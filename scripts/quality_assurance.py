import yaml
import netCDF4
import numpy as np
import xarray as xr
from functions import log, advanced_quality_flags
import glob
from ctd import ctd

lake_info = {"lat":46.49,"alt" :372.1}

log("Performing advanced quality check")
with open("scripts/input_python.yaml", "r") as f:
    directories = yaml.load(f, Loader=yaml.FullLoader)

folder = directories["Level1_dir"]
filelist = glob.glob(directories["Level1_dir"]+"/*.nc")
filelist.sort()
dataset = xr.open_mfdataset(filelist, decode_times=False)

advanced_dataset = advanced_quality_flags(dataset, json_path="quality_assurance.json")
dataset.close()

log("Update NetCDF files with new QA")
for file_path in filelist:
    dset = netCDF4.Dataset(file_path, 'r+')
    idx = np.where((advanced_dataset["time"] >= dset["time"][0]) & (advanced_dataset["time"] <= dset["time"][-1]))[0]
    for var in dset.variables:
        if "_qual" in var:
            dset[var][:] = np.array(advanced_dataset[var][idx], dtype=bool)
    dset.close()


for file_path in filelist: 
    CTD = ctd()
    CTD.read_processed_data(file_path)
    CTD.extract_profile()
    CTD.mask_data()
    CTD.derive_variables(lake_info["lat"], lake_info["alt"])
    CTD.quality_assurance()
    CTD.mask_data()
    CTD.to_netcdf(directories["Level2A_dir"], "L2A", mode="r+")
    Time_grid = CTD.data["time"][0]
    Press_grid = np.linspace(0, 120, 1201)
    CTD.profile_to_timeseries_grid(Press_grid, Time_grid)
    CTD.to_netcdf(directories["Level2B_dir"], "L2B", time_label='time_grid', output_period="yearly", mode="r+")
