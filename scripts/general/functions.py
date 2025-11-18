# -*- coding: utf-8 -*-
import os
import copy
import json
import ftplib
import netCDF4
import requests
import numpy as np
import pandas as pd
import xarray as xr
import seawater as sw
from shutil import move
from scipy.interpolate import griddata
from datetime import datetime, timedelta, timezone
from math import sin, cos, sqrt, atan2, radians
from dateutil.relativedelta import relativedelta
from envass import qualityassurance
import matplotlib.pyplot as plt


class GenericInstrument:
    def __init__(self, log=False):
        self.general_attributes = {
            "institution": "",
            "source": "",
            "references": "",
            "history": "",
            "conventions": "CF 1.7",
            "comment": "",
            "title": ""
        }
        self.dimensions = {}
        self.variables = {}
        self.data = {}
        self.grid = {}
        if log != False:
            self.log = log
        else:
            self.log = logger()

    def quality_assurance(self, file_path='./quality_assurance.json', maintenance_file = False, valid=False, time_label="time"):
        self.log.info("Applying quality assurance", indent=2)

        if not os.path.exists(file_path):
            self.log.warning("Cannot find QA file: {}, no QA applied.".format(file_path), indent=2)
            return False


        # Maintenance periods or sensor issues
        periods = []
        if maintenance_file:
            print("Processing maintenance periods from {}".format(maintenance_file))
            df = pd.read_csv(maintenance_file, sep=";")
            df["start"] = df["start"].apply(
                lambda x: datetime.timestamp(datetime.strptime(x, '%Y%m%d %H:%M:%S').replace(tzinfo=timezone.utc)))
            df["stop"] = df["stop"].apply(
                lambda x: datetime.timestamp(datetime.strptime(x, '%Y%m%d %H:%M:%S').replace(tzinfo=timezone.utc)))
            for d in df.to_dict('records'):
                periods.append(d)

#        try:
        quality_assurance_dict = json_converter(json.load(open(file_path)))
        for key, values in self.variables.copy().items():
            if "_qual" not in key and key in quality_assurance_dict:
                name = key + "_qual"
                self.variables[name] = {'var_name': name, 'dim': values["dim"],
                                        'unit': '0 = nothing to report, 1 = more investigation',
                                        'long_name': name, }
                if len(self.data[key]) == 1:
                    self.data[name] = [1]
                else:
                    qa = qualityassurance(np.array(self.data[key]), np.array(self.data[time_label]),
                                          **quality_assurance_dict[key]["simple"])
                    if valid:
                        time = np.array(self.data[time_label])
                        if min(time) < valid[0] < max(time) and min(time) < valid[1] < max(time):
                            qa[time < valid[0]] = 1
                            qa[time > valid[1]] = 1

                    if periods:
                        for period in periods:
                            time = np.array(self.data[time_label])
                            #sensor_id_list = ast.literal_eval(period["sensor_id"])
                            if key in period["parameter"]:
                                qa[np.logical_and(time > period["start"],time < period["stop"])] = 1
                        self.data[name] = qa
#        except:
#            self.log.error("Unable to apply QA file, this is likely due to bad formatting of the file.")

    def export(self, folder, title, output_period="file", time_label="time", grid=False, overwrite=False):
        if grid:
            variables = self.grid_variables
            dimensions = self.grid_dimensions
            data = self.grid
        else:
            variables = self.variables
            dimensions = self.dimensions
            data = self.data

        time = data[time_label]
        time_min = datetime.utcfromtimestamp(np.nanmin(time))
        time_max = datetime.utcfromtimestamp(np.nanmax(time))
        if output_period == "file":
            file_start = time_min
            file_period = time_max - time_min
        elif output_period == "daily":
            file_start = (time_min - timedelta(days=time_min.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            file_period = timedelta(days=1)
        elif output_period == "weekly":
            file_start = (time_min - timedelta(days=time_min.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            file_period = timedelta(weeks=1)
        elif output_period == "monthly":
            file_start = time_min.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            file_period = relativedelta(months=+1)
        elif output_period == "yearly":
            file_start = time_min.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            file_period = relativedelta(year=+1)
        else:
            self.log.warning('Output period "{}" not recognised.'.format(output_period), indent=2)
            return

        if not os.path.exists(folder):
            os.makedirs(folder)

        output_files = []
        while file_start < time_max:
            file_end = file_start + file_period
            filename = "{}_{}.nc".format(title, file_start.strftime('%Y%m%d_%H%M%S'))
            out_file = os.path.join(folder, filename)
            output_files.append(out_file)
            self.log.info("Writing {} data from {} until {} to NetCDF file {}".format(title, file_start, file_end, filename), indent=2)

            if not os.path.isfile(out_file):
                self.log.info("Creating new file.", indent=3)
                with netCDF4.Dataset(out_file, mode='w', format='NETCDF4') as nc:
                    for key in self.general_attributes:
                        setattr(nc, key, self.general_attributes[key])
                    for key, values in dimensions.items():
                        nc.createDimension(values['dim_name'], values['dim_size'])
                    for key, values in variables.items():
                        var = nc.createVariable(values["var_name"], np.float64, values["dim"], fill_value=np.nan)
                        var.units = values["unit"]
                        var.long_name = values["long_name"]
                        if grid and key == time_label:
                            var[0] = time[0]
                        elif grid and len(values["dim"]) == 2:
                            var[:, 0] = data[key]
                        else:
                            var[:] = data[key]
            else:
                self.log.info("Editing existing file.", indent=3)
                with netCDF4.Dataset(out_file, mode='a', format='NETCDF4') as nc:
                    nc_time = np.array(nc.variables[time_label][:])
                    if grid:
                        if time[0] in nc_time:
                            if overwrite:
                                self.log.info("Overwriting data at {}.".format(time[0]), indent=3)
                                idx = np.where(nc_time == time[0])[0][0]
                                for key, values in variables.items():
                                    if key not in dimensions:
                                        if len(values["dim"]) == 1:
                                            if hasattr(data[key], "__len__"):
                                                nc.variables[key][idx] = data[key][0]
                                            else:
                                                nc.variables[key][idx] = data[key]
                                        elif len(values["dim"]) == 2:
                                            nc.variables[key][:, idx] = data[key]
                                        else:
                                            self.log.warning("Unable to write {} with {} dimensions.".format(key, len(values["dim"])))

                            else:
                                self.log.info("Grid data already exists in NetCDF, skipping.", indent=3)
                        else:
                            idx = position_in_array(nc_time, time[0])
                            nc.variables[time_label][:] = np.insert(nc_time, idx, time[0])
                            for key, values in variables.items():
                                if key not in dimensions:
                                    var = nc.variables[key]
                                    if len(values["dim"]) == 1:
                                        if hasattr(data[key], "__len__"):
                                            var[idx] = data[key][0]
                                        else:
                                            var[idx] = data[key]
                                    elif len(values["dim"]) == 2:
                                        end = len(var[:][0]) - 1
                                        if idx != end:
                                            var[:, end] = data[key]
                                            var[:] = var[:, np.insert(np.arange(end), idx, end)]
                                        else:
                                            var[:, idx] = data[key]
                                    else:
                                        self.log.warning("Unable to write {} with {} dimensions.".format(key, len(values["dim"])))
                    else:
                        if np.all(np.isin(time, nc_time)) and not overwrite:
                            self.log.info("Data already exists in NetCDF, skipping.", indent=3)
                        else:
                            valid_time = (time >= datetime.timestamp(file_start)) & (time < datetime.timestamp(file_end))
                            non_duplicates = ~np.isin(time, nc_time)
                            valid = np.logical_and(valid_time, non_duplicates)
                            combined_time = np.append(nc_time, time[valid])
                            order = np.argsort(combined_time)
                            nc_copy = copy_variables(nc.variables)
                            for key, values in self.variables.items():
                                combined = np.append(nc_copy[key][:], np.array(data[key])[valid])
                                if overwrite:
                                    print(len(combined), len(time))
                                    combined[np.isin(combined_time, time)] = np.array(data[key])[np.isin(time, combined_time)]
                                out = combined[order]
                                nc.variables[key][:] = out
            file_start = file_start + file_period
        return output_files

    def mask_data(self):
        self.log.info("Masking L1 data.", indent=2)
        for var in self.variables:
            if var + "_qual" in self.data:
                idx = self.data[var + "_qual"][:] > 0
                self.data[var][idx] = np.nan

    def profile_to_timeseries_grid(self, time_label="time", depth_label="depth"):
        self.log.info("Resampling profile to fixed grid...", indent=2)
        try:
            self.grid[depth_label] = self.depths
        except:
            raise ValueError("self.depths must be defined as an fixed array of depths to produce timeseries grid.")
        self.grid[time_label] = [self.data[time_label][0]]
        for key, values in self.grid_variables.items():
            if key not in self.grid_dimensions:
                if len(values["dim"]) == 1:
                    if "depth" in values and "source" in values:
                        mask = (~np.isnan(self.data[values["source"]])) & (~np.isnan(self.data[depth_label]))
                        pressures = self.data[depth_label][mask]
                        data = self.data[values["source"]][mask]
                        self.grid[key] = np.interp([float(values["depth"])], pressures, data, left=np.nan, right=np.nan)
                    else:
                        self.log.warning('"depth" and "source" keys must be included in self.variables["{}"].'.format(key), indent=2)
                elif len(values["dim"]) == 2:
                    mask = (~np.isnan(self.data[key])) & (~np.isnan(self.data[depth_label]))
                    pressures = self.data[depth_label][mask]
                    data = self.data[key][mask]
                    if len(data) < 5:
                        self.grid[key] = np.asarray([np.nan] * len(self.depths))
                    else:
                        self.grid[key] = np.interp(self.depths, pressures, data, left=np.nan, right=np.nan)
                else:
                    self.log.warning("Unable to process data for {} with {} dimensions.".format(key, len(values["dim"])), indent=2)

    def read_netcdf_data(self, file):
        with netCDF4.Dataset(file, 'r') as nc:
            for key in nc.variables.keys():
                self.data[key] = np.array(nc.variables[key][:])


class logger(object):
    def __init__(self, path=False, time=True):
        if path != False:
            if os.path.exists(os.path.dirname(path)):
                path.split(".")[0]
                if time:
                    self.path = "{}_{}.log".format(path.split(".")[0], datetime.now().strftime("%H%M%S%f"))
                else:
                    self.path = "{}.log".format(path.split(".")[0])
            else:
                print("\033[93mUnable to find log folder: {}. Logs will be printed but not saved.\033[0m".format(os.path.dirname(path)))
                self.path = False
        else:
            self.path = False
        self.stage = 1

    def info(self, string, indent=0):
        out = datetime.now().strftime("%H:%M:%S.%f") + (" " * 3 * (indent + 1)) + string
        print(out)
        if self.path:
            with open(self.path, "a") as file:
                file.write(out + "\n")

    def initialise(self, string):
        out = "****** " + string + " ******"
        print('\033[1m' + out + '\033[0m')
        if self.path:
            with open(self.path, "a") as file:
                file.write(out + "\n")

    def begin_stage(self, string):
        self.newline()
        out = datetime.now().strftime("%H:%M:%S.%f") + "   Stage {}: ".format(self.stage) + string
        self.stage = self.stage + 1
        print('\033[95m' + out + '\033[0m')
        if self.path:
            with open(self.path, "a") as file:
                file.write(out + "\n")
        return self.stage - 1

    def end_stage(self):
        out = datetime.now().strftime("%H:%M:%S.%f") + "   Stage {}: Completed.".format(self.stage - 1)
        print('\033[92m' + out + '\033[0m')
        if self.path:
            with open(self.path, "a") as file:
                file.write(out + "\n")

    def warning(self, string, indent=0):
        out = datetime.now().strftime("%H:%M:%S.%f") + (" " * 3 * (indent + 1)) + "WARNING: " + string
        print('\033[93m' + out + '\033[0m')
        if self.path:
            with open(self.path, "a") as file:
                file.write(out + "\n")

    def error(self, stage):
        out = datetime.now().strftime("%H:%M:%S.%f") + "   ERROR: Script failed on stage {}".format(stage)
        print('\033[91m' + out + '\033[0m')
        if self.path:
            with open(self.path, "a") as file:
                file.write(out + "\n")
                file.write("\n")
                traceback.print_exc(file=file)

    def end(self, string):
        out = "****** " + string + " ******"
        print('\033[92m' + out + '\033[0m')
        if self.path:
            with open(self.path, "a") as file:
                file.write(out + "\n")

    def subprocess(self, process, error=""):
        failed = False
        while True:
            output = process.stdout.readline()
            out = output.strip()
            print(out)
            if error != "" and error in out:
                failed = True
            if self.path:
                with open(self.path, "a") as file:
                    file.write(out + "\n")
            return_code = process.poll()
            if return_code is not None:
                for output in process.stdout.readlines():
                    out = output.strip()
                    print(out)
                    if self.path:
                        with open(self.path, "a") as file:
                            file.write(out + "\n")
                break
        return failed

    def newline(self):
        print("")
        if self.path:
            with open(self.path, "a") as file:
                file.write("\n")


def get_bathymetry(file, depth):
    df_bath = pd.read_csv(file, header=0)
    df_bath["Isobath Area"] = df_bath["Isobath Area (m2)"].astype("float")
    df_bath["Depth"] = df_bath["Depth (m)"].astype("float")
    area = np.interp(depth, df_bath["Depth"], df_bath["Isobath Area"])
    return depth, area

def pressure_correction(T,altitude):
    mmHg_mb = 0.750061683
    mmHg_inHg = 25.3970886
    standard_pressure_sea_level = 29.92126
    standard_temperature_sea_level = 15 + 273.15
    gravitational_acceleration = 9.81
    air_molar_mass = 0.0289644
    universal_gas_constant = 8.31447
    baro = (1. / mmHg_mb) * mmHg_inHg * standard_pressure_sea_level * np.exp(
    (-gravitational_acceleration * air_molar_mass * altitude) / (
                universal_gas_constant * standard_temperature_sea_level))
    u = 10 ** (8.10765 - 1750.286 / (235 + T))
    press_corr = (baro * mmHg_mb - u) / (760 - u)
    return press_corr

def timeseries_quality_assurance(folder, period=365, time_label="time", datalakes=[], json_path="quality_assurance.json",
                                 events="notes/events.csv", log=logger()):
    log.info("Running timeseries quality assurance for {}".format(folder), indent=1)
    files = os.listdir(folder)
    files.sort()
    cutoff = datetime.now() - timedelta(days=period)
    process = []
    log.info("Filtering files to the last {} days.".format(period), indent=2)
    for file in files:
        if datetime.strptime(file.split("_")[-2], '%Y%m%d') > cutoff:
            process.append(os.path.join(folder, file))

    log.info("Opening and merging {} files with xarray.".format(len(process)), indent=2)
    with xr.open_mfdataset(process, decode_times=False) as ds:
        log.info("Resetting QA to allow removal of conditions", indent=3)
        for var in ds.variables.keys():
            if "_qual" in var:
                ds.variables[var][:] = 0
        ds = event_quality_flags(ds, datalakes, events, log, time_label=time_label)
        ds = advanced_quality_flags(ds, json_path, log, time_label=time_label)

    log.info("Writing outputs to NetCDF files.", indent=2)
    for file_path in process:
        with netCDF4.Dataset(file_path, 'r+') as dset:
            idx = np.where((ds["time"] >= dset["time"][0]) & (ds["time"] <= dset["time"][-1]))[0]
            for var in dset.variables:
                if "_qual" in var and time_label not in var:
                    dset[var][:] = np.array(ds[var][idx].values)
    return process


def advanced_quality_flags(ds, json_path, log, time_label="time"):
    log.info("Applying advanced timeseries checks.", indent=2)
    quality_assurance_dict = json_converter(json.load(open(json_path)))
    for var in quality_assurance_dict.keys():
        if var in quality_assurance_dict and var in ds and var + "_qual" in ds:
            simple = qualityassurance(np.array(ds[var]), np.array(ds[time_label]), **quality_assurance_dict[var]["simple"])
            ds[var + "_qual"][simple > 0] = 1
            data = np.array(ds[var]).copy()
            data[np.array(ds[var + "_qual"].values) > 0] = np.nan
            advanced = qualityassurance(data, np.array(ds[time_label]), **quality_assurance_dict[var]["advanced"])
            ds[var + "_qual"][advanced > 0] = 1
    return ds


def event_quality_flags(ds, datalakes, events, log, time_label="time"):
    log.info("Applying manual timeseries checks.", indent=2)
    df = pd.read_csv(events, sep=";")
    df["start"] = df["start"].apply(lambda l: datetime.timestamp(datetime.strptime(l, '%Y%m%d %H:%M:%S').replace(tzinfo=timezone.utc)))
    df["stop"] = df["stop"].apply(lambda l: datetime.timestamp(datetime.strptime(l, '%Y%m%d %H:%M:%S').replace(tzinfo=timezone.utc)))
    for id in datalakes:
        x = requests.get("https://api.datalakes-eawag.ch/maintenance/"+str(id))
        if x.status_code == 200:
            for e in x.json():
                df.loc[len(df)] = [datetime.timestamp(datetime.strptime(e["starttime"], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)),
                                   datetime.timestamp(datetime.strptime(e["endtime"], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)),
                                   e["parseparameter"],
                                   e["description"]]

    time = ds.variables["time"][:]
    for index, row in df.iterrows():
        idx = np.where(np.logical_and(time >= int(row["start"]), time <= int(row["stop"])))
        if row["parameter"] == "All":
            for var in ds.variables.keys():
                if "_qual" in var and time_label not in var:
                    ds.variables[var][:][idx] = 1
        else:
            if row["parameter"] + "_qual" in ds.variables.keys():
                ds.variables[row["parameter"] + "_qual"][:][idx] = 1
            else:
                log.warning("Unable to find local parameter {} to apply event.".format(row["parameter"] + "_qual"))
    return ds


def json_converter(qa):
    for keys in qa.keys():
        try:
            if qa[keys]["simple"]["bounds"][0] == "-inf":
                qa[keys]["simple"]["bounds"][0] = -np.inf
            if qa[keys]["simple"]["bounds"][1] == "inf":
                qa[keys]["simple"]["bounds"][1] = np.inf
        except:
            pass
    try:
        if qa["time"]["simple"]["bounds"][1] == "now":
            qa["time"]["simple"]["bounds"][1] = datetime.now().timestamp()
        return qa
    except:
        return qa


def files_in_directory(root):
    f = []
    for path, subdirs, files in os.walk(root):
        for name in files:
            f.append(os.path.join(path, name))
    return f


def geographic_distance(latlng1, latlng2):
    lat1 = radians(latlng1[0])
    lon1 = radians(latlng1[1])
    lat2 = radians(latlng2[0])
    lon2 = radians(latlng2[1])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return 6373000.0 * c


def copy_variables(variables_dict):
    var_dict = dict()
    for var in variables_dict:
        var_dict[var] = variables_dict[var][:]
    nc_copy = copy.deepcopy(var_dict)
    return nc_copy


def position_in_array(arr, value):
    for i in range(len(arr)):
        if value < arr[i]:
            return i
    return len(arr)