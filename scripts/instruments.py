# -*- coding: utf-8 -*-
import os
import json
import numpy as np
import pandas as pd
import seawater as sw
import pylake
import dateparser
from copy import deepcopy
from envass import qualityassurance
from datetime import datetime, timedelta, timezone
from general.functions import GenericInstrument
from functions import (parse_time, parse_chl, parse_file, check_variable, check_valid_profile,
                       first_centered_differences, json_converter, salinity, density,
                       potential_temperature_sw, oxygen_saturation, default_salinity_temperature)

class CTD(GenericInstrument):
    def __init__(self, *args, **kwargs):
        super(CTD, self).__init__(*args, **kwargs)
        self.water_entry_index = False
        self.bottom_of_profile_index = False
        self.air_press = False
        self.submerged_index = False
        self.depths = np.linspace(0, 120, 1201)

        self.general_attributes = {
            "institution": "EPFL",
            "source": "LéXPLORE CTD",
            "references": "LéXPLORE common instruments sebastien.lavanchy@epfl.ch",
            "history": "See history on Renku",
            "conventions": "CF 1.7",
            "comment": "Data from CTD profiles on Lexplore Platform in Lake Geneva",
            "title": "Lexplore CTD",
            "latitude": 46.49,
            "longitude": 6.67,
            "altitude" : 372.1,
        }

        self.dimensions = {
            'time': {'dim_name': 'time', 'dim_size': None}
        }

        self.variables = {
            'time': {'var_name': 'time', 'dim': ('time',), 'unit': 'seconds since 1970-01-01 00:00:00',
                     'long_name': 'time', "function": parse_time},
            'Press': {'var_name': 'Press', 'dim': ('time',), 'unit': 'dbar', 'long_name': 'pressure'},
            'Temp': {'var_name': 'Temp', 'dim': ('time',), 'unit': 'degC', 'long_name': 'temperature'},
            'Cond': {'var_name': 'Cond', 'dim': ('time',), 'unit': 'mS/cm', 'long_name': 'conductivity'},
            'Chl_A': {'var_name': 'Chl_A', 'dim': ('time',), 'unit': 'µg/l', 'long_name': 'chlorophyll A',
                      "function": parse_chl},
            'Turb': {'var_name': 'Turb', 'dim': ('time',), 'unit': 'FTU', 'long_name': 'Turbidity'},
            'pH': {'var_name': 'pH', 'dim': ('time',), 'unit': '_', 'long_name': 'pH'},
            'sat': {'var_name': 'sat', 'dim': ('time',), 'unit': '%', 'long_name': 'oxygen saturation'},
            'DO_mg': {'var_name': 'DO_mg', 'dim': ('time',), 'unit': 'mg/l', 'long_name': 'oxygen concentration'},
        }

        self.derived_variables = {
            "rho": {'var_name': "rho", 'dim': ('time',), 'unit': 'kg/m3', 'long_name': "Density", },
            "depth": {'var_name': "depth", 'dim': ('time',), 'unit': 'm', 'long_name': "Depth", },
            "pt": {'var_name': "pt", 'dim': ('time',), 'unit': 'degC', 'long_name': "Potential Temperature", },
            "prho": {'var_name': "prho", 'dim': ('time',), 'unit': 'kg/m3', 'long_name': "Potential Density", },
            "thorpe": {'var_name': "thorpe", 'dim': ('time',), 'unit': 'm', 'long_name': "Thorpe Displacements", },
            "SALIN": {'var_name': 'SALIN', 'dim': ('time',), 'unit': ['PSU', 'ppt'], 'long_name': 'salinity', }
        }

        # Events flagging a measured variable also flag the variables derived from it in derive_variables
        self.event_propagation = {
            "Temp": ["SALIN", "rho", "depth", "pt", "prho", "sat", "thorpe"],
            "Cond": ["SALIN", "rho", "depth", "pt", "prho", "sat", "thorpe"],
            "Press": ["depth", "pt", "prho", "sat", "thorpe"],
            "DO_mg": ["sat"],
        }

        self.grid_dimensions = {
            'time': {'dim_name': 'time', 'dim_size': None},
            'depth': {'dim_name': 'depth', 'dim_size': None}
        }

        self.grid_variables = {
            'time': {'var_name': 'time', 'dim': ('time',), 'unit': 'seconds since 1970-01-01 00:00:00',
                     'long_name': 'time'},
            "depth": {'var_name': "depth", 'dim': ('depth',), 'unit': 'm', 'long_name': "Depth", },
            'Temp': {'var_name': 'Temp', 'dim': ('depth', 'time'), 'unit': 'degC', 'long_name': 'temperature'},
            'Cond': {'var_name': 'Cond', 'dim': ('depth', 'time'), 'unit': 'mS/cm', 'long_name': 'conductivity'},
            'Chl_A': {'var_name': 'Chl_A', 'dim': ('depth', 'time'), 'unit': 'g/l', 'long_name': 'chlorophyll A'},
            'Turb': {'var_name': 'Turb', 'dim': ('depth', 'time'), 'unit': 'FTU', 'long_name': 'Turbidity'},
            'pH': {'var_name': 'pH', 'dim': ('depth', 'time'), 'unit': '_', 'long_name': 'pH'},
            'sat': {'var_name': 'sat', 'dim': ('depth', 'time'), 'unit': '%', 'long_name': 'oxygen saturation'},
            'DO_mg': {'var_name': 'DO_mg', 'dim': ('depth', 'time'), 'unit': 'mg/l',
                      'long_name': 'oxygen concentration'},
            "rho": {'var_name': "rho", 'dim': ('depth', 'time'), 'unit': 'kg/m3', 'long_name': "Density", },
            "pt": {'var_name': "pt", 'dim': ('depth', 'time'), 'unit': 'degC', 'long_name': "Potential Temperature", },
            "prho": {'var_name': "prho", 'dim': ('depth', 'time'), 'unit': 'kg/m3', 'long_name': "Potential Density"},
            "thorpe": {'var_name': "thorpe", 'dim': ('depth', 'time'), 'unit': 'm', 'long_name': "Thorpe Displacements"},
            "SALIN": {'var_name': 'SALIN', 'dim': ('depth', 'time'), 'unit': 'PSU', 'long_name': 'salinity'}
        }
        self.data = {}
        self.grid = {}

    def read_data(self, file):
        self.log.info("Reading data from {}".format(file), 1)
        try:
            with open(file, encoding="utf8", errors='ignore') as f:
                lines = f.readlines()
            try:
                ref_date = datetime.timestamp(dateparser.parse(lines[2].strip()))
            except:
                self.log.warning("Unable to convert date: {}".format(lines[2].strip()), indent=2)
                ref_date = False

            skip_rows, columns, units, valid, date_format = parse_file(file, "Lines :")
            if not valid:
                return False
            df = pd.read_csv(file, sep='\s+', header=None, skiprows=skip_rows, names=columns, engine='python', encoding="cp1252")

            for variable in self.variables:
                if check_variable(variable, self.variables[variable]["unit"], columns, units):
                    self.data[variable] = np.array(df[variable].values)
                elif "function" in self.variables[variable]:
                    self.data[variable] = np.array(
                        self.variables[variable]["function"](df, self.variables[variable], variable, columns, units,
                                                             ref_date, date_format))
                else:
                    self.data[variable] = np.array([np.nan] * len(df))

            if self.data["time"][0] > datetime.utcnow().timestamp() or not check_valid_profile(self.data["Press"], 1):
                return False

            return True
        except Exception as e:
            self.log.info("Failed to read data from {}".format(file), indent=1)
            print(e)
            return False

    def extract_profile(self, remove_timesteps=3):
        self.log.info("Extracting profile...", indent=1)
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
        self.log.info("Applying quality assurance", indent=1)
        quality_assurance_dict = json_converter(json.load(open(file_path)))
        for key, values in self.variables.copy().items():
            if "_qual" not in key:
                if (quality_assurance_dict[key]["advanced"]) or (quality_assurance_dict[key]["simple"]):
                    name = key + "_qual"
                    self.variables[name] = {'var_name': name, 'dim': values["dim"],
                                            'unit': '0 = nothing to report, 1 = more investigation',
                                            'long_name': name, }
                    if simple:
                        self.data[name] = qualityassurance(np.array(self.data[key]), np.array(self.data["time"]),
                                                           **quality_assurance_dict[key]["simple"])
                    else:
                        quality_assurance_all = dict(quality_assurance_dict[key]["simple"],
                                                     **quality_assurance_dict[key]["advanced"])
                        self.data[name] = qualityassurance(np.array(self.data[key]), np.array(self.data["time"]),
                                                           **quality_assurance_all)
                    if key != "time":
                        if self.bottom_of_profile_index:
                            self.data[name][self.bottom_of_profile_index:] = 1
                        if self.water_entry_index:
                            self.data[name][:self.water_entry_index] = 1


    def derive_variables(self, lat, alt, y_cond=0.874e-3, beta=0.807e-3):
        self.log.info("Calculating derived variables...", indent=1)
        data = deepcopy(self.data)
        self.log.info("Masking variables for calculations", indent=2)
        for var in self.variables:
            if "_qual" not in var:
                idx = data[var + "_qual"] > 0
                data[var][idx] = np.nan

        data["adj_press"] = data["Press"] - self.air_press
        threshold = data["Temp"].shape[0] * 0.9
        if sum(np.isnan(data["Temp"])) > threshold or sum(np.isnan(data["Cond"])) > threshold or \
                sum(np.isnan(data["adj_press"])) > threshold:
            self.log.info("Not enough valid parameters for derived variables.", indent=2)
            return False
        else:
            self.variables.update(self.derived_variables)

        try:
            self.log.info("Calculating salinity...", indent=2)
            self.data["SALIN"] = salinity(data["Temp"], data["Cond"], y_cond,
                                          temperature_func=default_salinity_temperature)
        except Exception:
            self.log.info("Failed to calculate salinity", indent=2)
            return False

        try:
            self.log.info("Calculating density...", indent=2)
            self.data["rho"] = np.asarray([1000] * len(data["Press"]))
            self.data["rho"] = density(data["Temp"], self.data["SALIN"])
        except Exception:
            self.log.info("Failed to calculate density", indent=2)
            return False

        self.log.info("Calculating depth...", indent=2)
        self.data["depth"] = 1e4 * data["adj_press"] / self.data["rho"] / sw.g(lat)

        try:
            self.log.info("Calculating potential temperature...", indent=2)
            self.data["pt"] = potential_temperature_sw(data["Temp"], self.data["SALIN"], data["adj_press"], 0)
        except Exception:
            self.data["pt"] = np.asarray([np.nan] * len(data["time"]))
            self.log.info("Failed to calculate potential temperature")

        try:
            self.log.info("Calculating potential density...", indent=2)
            self.data["prho"] = density(self.data["pt"], self.data["SALIN"])
        except Exception:
            self.log.info("Failed to calculate potential density", indent=2)

        try:
            self.log.info("Calculating oxygen saturation...", indent=2)
            theoretical_saturation = oxygen_saturation(self.data["pt"], self.data["SALIN"], alt, lat)
            self.data["sat"] = (self.data["DO_mg"] / theoretical_saturation) * 100
        except Exception:
            self.log.info("Failed to replace oxygen saturation", indent=2)

        try:
            self.log.info("Calculating Thorpe Dispacements...", indent=2)
            sorted_pt = np.argsort(self.data["pt"])[::-1]
            self.data["thorpe"] = -(self.data["depth"] - self.data["depth"][sorted_pt])
        except Exception:
            self.log.info("Failed to calculate Thorpe Displacements", indent=2)

        return True