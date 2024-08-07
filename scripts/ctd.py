# -*- coding: utf-8 -*-
import os
import netCDF4
import dateparser
import numpy as np
import pandas as pd
from copy import deepcopy
from envass import qualityassurance
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from functions import *


class ctd:
    def __init__(self):
        self.water_entry_index = False
        self.bottom_of_profile_index = False
        self.air_press = False
        self.submerged_index = False
        self.fixed_depths = np.linspace(0, 120, 1201)

        self.general_attributes = {
            "institution": "EPFL",
            "source": "LéXPLORE CTD",
            "references": "LéXPLORE common instruments sebastien.lavanchy@epfl.ch",
            "history": "See history on Renku",
            "conventions": "CF 1.7",
            "comment": "Data from CTD profiles on Lexplore Platform in Lake Geneva",
            "title": "Lexplore CTD"
        }

        self.dimensions = {
            'time': {'dim_name': 'time', 'dim_size': None}
        }

        self.variables = {
            'time': {'var_name': 'time', 'dim': ('time',), 'unit': 'seconds since 1970-01-01 00:00:00',
                     'longname': 'time', "function": parse_time},
            'Press': {'var_name': 'Press', 'dim': ('time',), 'unit': 'dbar', 'longname': 'pressure'},
            'Temp': {'var_name': 'Temp', 'dim': ('time',), 'unit': 'degC', 'longname': 'temperature'},
            'Cond': {'var_name': 'Cond', 'dim': ('time',), 'unit': 'mS/cm', 'longname': 'conductivity'},
            'Chl_A': {'var_name': 'Chl_A', 'dim': ('time',), 'unit': 'µg/l', 'longname': 'chlorophyll A',
                      "function": parse_chl},
            'Turb': {'var_name': 'Turb', 'dim': ('time',), 'unit': 'FTU', 'longname': 'Turbidity'},
            'pH': {'var_name': 'pH', 'dim': ('time',), 'unit': '_', 'longname': 'pH'},
            'sat': {'var_name': 'sat', 'dim': ('time',), 'unit': '%', 'longname': 'oxygen saturation'},
            'DO_mg': {'var_name': 'DO_mg', 'dim': ('time',), 'unit': 'mg/l', 'longname': 'oxygen concentration'},
        }

        self.derived_variables = {
            "rho": {'var_name': "rho", 'dim': ('time',), 'unit': 'kg/m3', 'longname': "Density", },
            "depth": {'var_name': "depth", 'dim': ('time',), 'unit': 'm', 'longname': "Depth", },
            "pt": {'var_name': "pt", 'dim': ('time',), 'unit': 'degC', 'longname': "Potential Temperature", },
            "prho": {'var_name': "prho", 'dim': ('time',), 'unit': 'kg/m3', 'longname': "Potential Density", },
            "thorpe": {'var_name': "thorpe", 'dim': ('time',), 'unit': 'm', 'longname': "Thorpe Displacements", },
            "SALIN": {'var_name': 'SALIN', 'dim': ('time',), 'unit': ['PSU', 'ppt'], 'longname': 'salinity', }
        }

        self.grid_dimensions = {
            'time': {'dim_name': 'time', 'dim_size': None},
            'depth': {'dim_name': 'depth', 'dim_size': None}
        }

        self.grid_variables = {
            'time': {'var_name': 'time', 'dim': ('time',), 'unit': 'seconds since 1970-01-01 00:00:00',
                     'longname': 'time'},
            "depth": {'var_name': "depth", 'dim': ('depth',), 'unit': 'm', 'longname': "Depth", },
            'Temp': {'var_name': 'Temp', 'dim': ('depth', 'time'), 'unit': 'degC', 'longname': 'temperature'},
            'Cond': {'var_name': 'Cond', 'dim': ('depth', 'time'), 'unit': 'mS/cm', 'longname': 'conductivity'},
            'Chl_A': {'var_name': 'Chl_A', 'dim': ('depth', 'time'), 'unit': 'g/l', 'longname': 'chlorophyll A'},
            'Turb': {'var_name': 'Turb', 'dim': ('depth', 'time'), 'unit': 'FTU', 'longname': 'Turbidity'},
            'pH': {'var_name': 'pH', 'dim': ('depth', 'time'), 'unit': '_', 'longname': 'pH'},
            'sat': {'var_name': 'sat', 'dim': ('depth', 'time'), 'unit': '%', 'longname': 'oxygen saturation'},
            'DO_mg': {'var_name': 'DO_mg', 'dim': ('depth', 'time'), 'unit': 'mg/l',
                      'longname': 'oxygen concentration'},
            "rho": {'var_name': "rho", 'dim': ('depth', 'time'), 'unit': 'kg/m3', 'longname': "Density", },
            "pt": {'var_name': "pt", 'dim': ('depth', 'time'), 'unit': 'degC', 'longname': "Potential Temperature", },
            "prho": {'var_name': "prho", 'dim': ('depth', 'time'), 'unit': 'kg/m3', 'longname': "Potential Density"},
            "thorpe": {'var_name': "thorpe", 'dim': ('depth', 'time'), 'unit': 'm', 'longname': "Thorpe Displacements"},
            "SALIN": {'var_name': 'SALIN', 'dim': ('depth', 'time'), 'unit': 'PSU', 'longname': 'salinity'}
        }
        self.data = {}
        self.grid = {}

    def read_raw_data(self, infile):
        log("Reading data from {}".format(infile))
        with open(infile, encoding="utf8", errors='ignore') as f:
            lines = f.readlines()
        try:
            ref_date = datetime.timestamp(dateparser.parse(lines[2]))
        except:
            log("Unable to convert date: {}".format(lines[2]))
            ref_date = False

        skip_rows, columns, units, valid, date_format = parse_file(infile, "Lines :")
        if not valid:
            return False
        df = pd.read_csv(infile, delim_whitespace=True, header=None, skiprows=skip_rows, names=columns, engine='python',
                         encoding="cp1252")

        for variable in self.variables:
            if check_variable(variable, self.variables[variable]["unit"], columns, units):
                self.data[variable] = np.array(df[variable].values)
            elif "function" in self.variables[variable]:
                self.data[variable] = np.array(
                    self.variables[variable]["function"](df, self.variables[variable], variable, columns, units,
                                                         ref_date, date_format))
            else:
                self.data[variable] = np.array([-999] * len(df))

        if self.data["time"][0] > datetime.utcnow().timestamp():
            return False

        if not check_valid_profile(self.data["Press"], 1):
            return False

        return True

    def extract_profile(self, remove_timesteps=3):
        log("Extracting profile...", indent=1)
        self.data["Press"] = np.array([float(i) for i in self.data["Press"]])
        self.water_entry_index = 0
        self.submerged_index = 0
        self.bottom_of_profile_index = len(self.data["Press"])

        if not np.isnan(self.data["Cond"]).all():
            diff_cond = first_centered_differences(np.arange(len(self.data["Cond"])), self.data["Cond"])
            perc_cond = np.where(diff_cond > np.percentile(diff_cond, 85))
            water_entry_index = perc_cond[0][0]
            submerged_index = perc_cond[0][0]
            for i in range(len(perc_cond[0]) - 1):
                if perc_cond[0][i + 1] - perc_cond[0][i] != 1:
                    submerged_index = perc_cond[0][i]
                    break
            if len(self.data["Press"]) > water_entry_index > 0:
                self.water_entry_index = water_entry_index - 1
            if len(self.data["Press"]) > submerged_index > 0:
                self.submerged_index = submerged_index + 1

        self.bottom_of_profile_index = np.argmax(self.data["Press"]) - remove_timesteps

        if self.water_entry_index > 0:
            self.air_press = np.nanmean(self.data["Press"][:self.water_entry_index])
        else:
            self.air_press = np.nanmin(self.data["Press"][:self.bottom_of_profile_index])

    def quality_assurance(self, file_path='./quality_assurance.json', simple=True):
        log("Applying quality assurance", indent=1)
        quality_assurance_dict = json_converter(json.load(open(file_path)))
        for key, values in self.variables.copy().items():
            if "_qual" not in key:
                if (quality_assurance_dict[key]["advanced"]) or (quality_assurance_dict[key]["simple"]):
                    name = key + "_qual"
                    self.variables[name] = {'var_name': name, 'dim': values["dim"],
                                            'unit': '0 = nothing to report, 1 = more investigation',
                                            'longname': name, }
                    if simple:
                        self.data[name] = qualityassurance(np.array(self.data[key]), np.array(self.data["time"]),
                                                           **quality_assurance_dict[key]["simple"])
                    else:
                        quality_assurance_all = dict(quality_assurance_dict[key]["simple"],
                                                     **quality_assurance_dict[key]["advanced"])
                        self.data[name] = qualityassurance(np.array(self.data[key]), np.array(self.data["time"]),
                                                           **quality_assurance_all)
                    if key != "time":
                        self.data[name] = self.quality_assurance_ctd(self.data[name])

    def quality_assurance_ctd(self, qa):

        if self.bottom_of_profile_index:
            qa[self.bottom_of_profile_index:] = 1

        if self.water_entry_index:
            qa[:self.water_entry_index] = 1

        return qa

    def to_netcdf(self, folder, title, output_period="profile", mode='a', time_label="time", grid=False, ):

        if not os.path.exists(folder):
            os.makedirs(folder)

        if grid:
            variables = self.grid_variables
            dimensions = self.grid_dimensions
            data = self.grid
        else:
            variables = self.variables
            dimensions = self.dimensions
            data = self.data

        time_arr = data[time_label]
        dt_min = datetime.utcfromtimestamp(np.nanmin(time_arr))
        dt_max = datetime.utcfromtimestamp(np.nanmax(time_arr))

        if output_period == "weekly":
            start = (dt_min - timedelta(days=dt_min.weekday())).replace(hour=0, minute=0, second=0)
            td = timedelta(weeks=1)
        elif output_period == "monthly":
            start = dt_min.replace(day=1, hour=0, minute=0, second=0)
            td = relativedelta(months=+1)
        elif output_period == "yearly":
            start = dt_min.replace(month=1, day=1, hour=0, minute=0, second=0)
            td = start.replace(year=start.year + 1) - start
        elif output_period == "profile":
            start = dt_min
            td = dt_max - dt_min
        else:
            log("Output periods {} not defined.".format(output_period))
            return

        while start < dt_max:
            end = start + td
            s = datetime.timestamp(start)
            e = datetime.timestamp(end)

            filename = "{}_{}.nc".format(title, start.strftime('%Y%m%d_%H%M%S'))
            out_file = os.path.join(folder, filename)
            log("Writing {} data from {} until {} to NetCDF file {}".format(title, start, end, filename), 1)

            if os.path.isfile(out_file):
                nc = netCDF4.Dataset(out_file, mode=mode, format='NETCDF4')
                nc_time = nc.variables[time_label]

                if time_arr[0] in nc_time:
                    log("Duplicated run, no data added", 2)
                    nc.close()
                    start = start + td
                    continue
                else:
                    idx = position_in_array(nc_time, time_arr[0])
                    nc_time[:] = np.insert(nc_time[:], idx, time_arr[0])
                    for key, values in variables.items():
                        if key not in dimensions:
                            var = nc.variables[key]
                            end = len(var[:][0]) - 1
                            if idx != end:
                                var[:, end] = data[key]
                                var[:] = var[:, np.insert(np.arange(end), idx, end)]
                            else:
                                var[:, idx] = data[key]
                    nc.close()

            else:
                nc = netCDF4.Dataset(out_file, mode='w', format='NETCDF4')

                for key in self.general_attributes:
                    setattr(nc, key, self.general_attributes[key])

                for key, values in dimensions.items():
                    nc.createDimension(values['dim_name'], values['dim_size'])

                for key, values in variables.items():
                    var = nc.createVariable(values["var_name"], np.float64, values["dim"], fill_value=np.nan)
                    var.units = values["unit"]
                    var.long_name = values["longname"]
                    if len(values["dim"]) == 1:
                        var[:] = data[key]
                    elif len(values["dim"]) == 2:
                        var[:, 0] = data[key]

                nc.close()

            start = start + td

    def profile_to_timeseries_grid(self):
        log("Resampling profile to fixed grid...", indent=2)
        self.grid["depth"] = self.fixed_depths
        self.grid["time"] = [self.data["time"][0]]
        for key, values in self.grid_variables.items():
            if key not in self.grid_dimensions:
                mask = (~np.isnan(self.data[key])) & (~np.isnan(self.data["depth"]))
                depths = self.data["depth"][mask]
                data = self.data[key][mask]
                if len(data) < 50:
                    self.grid[key] = np.asarray([np.nan] * len(self.fixed_depths))
                else:
                    self.grid[key] = np.interp(self.fixed_depths, depths, data, left=np.nan, right=np.nan)

    def derive_variables(self, lat, alt, y_cond=0.874e-3, beta=0.807e-3):
        log("Calculating derived variables...", indent=1)
        data = deepcopy(self.data)
        log("Masking variables for calculations", indent=2)
        for var in self.variables:
            if "_qual" not in var:
                idx = data[var + "_qual"] > 0
                data[var][idx] = np.nan

        data["adj_press"] = data["Press"] - self.air_press
        threshold = data["Temp"].shape[0] * 0.9
        if sum(np.isnan(data["Temp"])) > threshold or sum(np.isnan(data["Cond"])) > threshold or \
                sum(np.isnan(data["adj_press"])) > threshold:
            log("Not enough valid parameters for derived variables.", indent=2)
            return False
        else:
            self.variables.update(self.derived_variables)

        try:
            log("Calculating salinity...", indent=2)
            self.data["SALIN"] = salinity(data["Temp"], data["Cond"], y_cond,
                                          temperature_func=default_salinity_temperature)
        except Exception:
            log("Failed to calculate salinity", indent=2)
            return False

        try:
            log("Calculating density...", indent=2)
            self.data["rho"] = np.asarray([1000] * len(data["Press"]))
            self.data["rho"] = density(data["Temp"], self.data["SALIN"])
        except Exception:
            log("Failed to calculate density", indent=2)
            return False

        log("Calculating depth...", indent=2)
        self.data["depth"] = 1e4 * data["adj_press"] / self.data["rho"] / sw.g(lat)

        try:
            log("Calculating potential temperature...", indent=2)
            self.data["pt"] = potential_temperature_sw(data["Temp"], self.data["SALIN"], data["adj_press"], 0)
        except Exception:
            self.data["pt"] = np.asarray([np.nan] * len(data["time"]))
            log("Failed to calculate potential temperature")

        try:
            log("Calculating potential density...", indent=2)
            self.data["prho"] = density(self.data["pt"], self.data["SALIN"])
        except Exception:
            log("Failed to calculate potential density", indent=2)

        try:
            log("Calculating oxygen saturation...", indent=2)
            theoretical_saturation = oxygen_saturation(self.data["pt"], self.data["SALIN"], alt, lat)
            self.data["sat"] = (self.data["DO_mg"] / theoretical_saturation) * 100
        except Exception:
            log("Failed to replace oxygen saturation", indent=2)

        try:
            log("Calculating Thorpe Dispacements...", indent=2)
            sorted_pt = np.argsort(self.data["pt"])[::-1]
            self.data["thorpe"] = -(self.data["depth"] - self.data["depth"][sorted_pt])
        except Exception:
            log("Failed to calculate Thorpe Displacements", indent=2)

        return True

    def mask_data(self):
        for var in self.variables:
            if "_qual" not in var:
                idx = self.data[var + "_qual"] > 0
                self.data[var][idx] = np.nan

    def read_processed_data(self, file):
        self.data = netCDF4.Dataset(file, 'r').variables
        for key in self.data.keys():
            self.data[key] = self.data[key][:]
