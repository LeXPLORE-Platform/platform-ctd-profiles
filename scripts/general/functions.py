# -*- coding: utf-8 -*-
import io
import os
import re
import csv
import copy
import json
import ftplib
import netCDF4
import numpy as np
import pandas as pd
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

    def quality_assurance(self, file_path='./quality_assurance.json', valid=False, time_label="time"):
        self.log.info("Applying quality assurance", indent=2)

        if not os.path.exists(file_path):
            self.log.warning("Cannot find QA file: {}, no QA applied.".format(file_path), indent=2)
            return False

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
                    self.data[name] = qa

    def apply_events(self, events_file, time_label="time", depth_label="depth", flag=1, profile=False):
        """Set flag in the _qual variables for every event in events_file that overlaps this data.
        With profile=True the data is a single profile: an event that overlaps it in time applies to the whole
        profile, and only its depth spec limits which points are flagged.
        Problems with the events file are logged as warnings and never stop processing."""
        self.log.info("Applying events from {}".format(events_file), indent=2)
        self.event_depth_windows = {}
        try:
            if not os.path.exists(events_file):
                self.log.warning("Cannot find events file: {}, no events applied.".format(events_file), indent=2)
                return False
            events = parse_events(events_file, self.log)
            if events is None:
                return False

            time = np.array(self.data[time_label], dtype=float)
            depths = np.array(self.data[depth_label], dtype=float) if depth_label in self.data else None
            tol = depth_tolerance(getattr(self, "depths", None), depths)
            propagation = getattr(self, "event_propagation", {})
            events = [e for e in events if e["start"] <= np.nanmax(time) and e["stop"] >= np.nanmin(time)]
            if not events:
                self.log.info("No events overlap this data.", indent=3)
        except Exception as e:
            self.log.warning("Unable to apply events from {} ({}: {}), no events applied.".format(
                events_file, type(e).__name__, e), indent=2)
            return False

        for event in events:
            try:
                self.apply_event(event, time, depths, tol, propagation, time_label, flag, profile)
            except Exception as e:
                self.log.warning("Unable to apply event on line {} ({}: {}), skipped.".format(
                    event["line"], type(e).__name__, e), indent=3)
        return True

    def apply_event(self, event, time, depths, tol, propagation, time_label, flag, profile=False):
        line = event["line"]
        self.log.info("Line {}: {} (parameter: {}, depth: {})".format(
            line, event["comments"], event["parameter"], event["depth"] or "All"), indent=3)

        variables = event_variables(event["parameter"], self.variables, time_label=time_label)
        for parameter in variables["unknown"]:
            self.log.warning("Unknown parameter {} in events line {}".format(parameter, line), indent=4)
        qual = list(variables["qual"])
        for name in variables["qual"]:
            added = [d + "_qual" for d in propagation.get(name[:-len("_qual")], [])
                     if d + "_qual" in self.variables and d + "_qual" not in qual]
            if added:
                self.log.info("{} also flags derived variables: {}".format(name, ", ".join(added)), indent=4)
                qual.extend(added)
        if not qual:
            self.log.warning("Event on line {} matches no variable, nothing flagged.".format(line), indent=4)
            return

        if profile:
            time_mask = np.ones(len(time), dtype=bool)
        else:
            time_mask = (time >= event["start"]) & (time <= event["stop"])
        if not time_mask.any():
            self.log.warning("Event on line {} falls in a gap in the data, nothing flagged.".format(line), indent=4)
            return

        spec = event["depth"]
        if spec == "" or spec.lower() == "all":
            items = [(time_mask, -np.inf, np.inf)]
        else:
            if depths is None:
                self.log.warning("Event on line {} has depth {} but the data has no depth, skipped.".format(line, spec), indent=4)
                return
            unflagged = np.logical_or.reduce([np.array(self.data[name]) == 0 for name in qual])
            missing = int(np.sum(time_mask & np.isnan(depths) & unflagged))
            if missing:
                self.log.warning("{} unflagged points in the event on line {} have no depth and are not flagged by it.".format(missing, line), indent=4)
            items = parse_event_depths(spec, np.where(time_mask, depths, np.nan), self.log, line, tol)
            if items is None:
                return
        mask = np.logical_or.reduce([m for m, _, _ in items])
        if not mask.any():
            self.log.warning("Event on line {} matches no depth in the data, nothing flagged.".format(line), indent=4)
            return

        windows = []
        if depths is not None:
            for m, low, high in items:
                d = depths[m & np.isfinite(depths)]
                if len(d):
                    windows.append((max(low, np.min(d) - tol), min(high, np.max(d) + tol)))
        for name in qual:
            values = np.array(self.data[name])
            values[mask] = np.bitwise_or(values[mask].astype(int), flag)
            self.data[name] = values
            self.event_depth_windows.setdefault(name[:-len("_qual")], []).extend(windows)
        self.log.info("Flagged {} points for {}".format(int(mask.sum()), ", ".join(qual)), indent=4)

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

    def mask_grid_events(self, depth_label="depth"):
        """Blank grid bins inside the depth range flagged by events, which the interpolation in
        profile_to_timeseries_grid would otherwise fill from the unflagged points either side."""
        windows = getattr(self, "event_depth_windows", {})
        if not windows:
            return
        self.log.info("Masking grid data flagged by events.", indent=2)
        grid_depths = np.array(self.grid[depth_label], dtype=float)
        for var, ranges in windows.items():
            if var not in self.grid or var in self.grid_dimensions or not ranges:
                continue
            values = np.array(self.grid[var], dtype=float)
            if values.shape != grid_depths.shape:
                self.log.warning("Unable to mask events in grid for {} with shape {}.".format(var, values.shape), indent=3)
                continue
            in_window = np.zeros(len(grid_depths), dtype=bool)
            for low, high in ranges:
                in_window |= (grid_depths >= low) & (grid_depths <= high)
            values[in_window] = np.nan
            self.grid[var] = values

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

EVENT_COLUMNS = ["start", "stop", "parameter", "depth", "comments"]


def parse_events(events_file, log):
    """Read an events file (start;stop;parameter;depth;comments) and return a list of events with start/stop as
    epoch seconds. An empty stop means the event is ongoing. Malformed rows are reported and skipped.
    Returns None if the file cannot be used at all."""
    try:
        try:
            with open(events_file, encoding="utf-8-sig", newline="") as f:
                text = f.read()
        except UnicodeDecodeError:
            log.warning("Events file {} is not UTF-8, reading it as Latin-1. Please save it as UTF-8.".format(events_file), indent=2)
            with open(events_file, encoding="latin-1", newline="") as f:
                text = f.read()
        reader = csv.reader(io.StringIO(text), delimiter=";")
        header = next(reader, None)
        if header is None:
            log.warning("Events file {} is empty, no events applied.".format(events_file), indent=2)
            return None
        header = [c.strip().lstrip("\ufeff").lower() for c in header]
        missing = [c for c in EVENT_COLUMNS if c not in header]
        if missing:
            log.warning("Events file {} missing columns: {}, no events applied.".format(events_file, ", ".join(missing)), indent=2)
            return None

        now = datetime.now(timezone.utc).timestamp()
        events = []
        for row in reader:
            line = reader.line_num
            if not any(c.strip() for c in row):
                continue
            if len(row) > len(header) and not any(c.strip() for c in row[len(header):]):
                row = row[:len(header)]
            if len(row) != len(header):
                log.warning("Invalid event on line {} of {} ({} fields, expected {}; quote comments containing ';'), skipped.".format(
                    line, events_file, len(row), len(header)), indent=3)
                continue
            event = {c: row[header.index(c)].strip() for c in EVENT_COLUMNS}
            start = parse_event_time(event["start"])
            stop = now if event["stop"] == "" else parse_event_time(event["stop"])
            if event["start"] == "":
                problem = "empty start"
            elif start is None:
                problem = "unable to parse start '{}'".format(event["start"])
            elif stop is None:
                problem = "unable to parse stop '{}'".format(event["stop"])
            elif stop < start:
                problem = "stop before start"
            elif event["parameter"] == "":
                problem = "empty parameter"
            else:
                event.update({"start": start, "stop": stop, "line": line})
                events.append(event)
                continue
            log.warning("Invalid event on line {} of {} ({}), skipped.".format(line, events_file, problem), indent=3)
        return events
    except Exception as e:
        log.warning("Unable to read events file {} ({}: {}), no events applied.".format(events_file, type(e).__name__, e), indent=2)
        return None


def parse_event_time(value):
    if not re.fullmatch(r"\d{8} \d{2}:\d{2}:\d{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y%m%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def event_variables(parameter, variables, time_label="time"):
    """Map an events parameter ("All" or comma separated variable names) to the matching _qual variables."""
    qual = [k for k in variables if k.endswith("_qual") and k != time_label + "_qual"]
    if parameter.strip().lower() == "all":
        return {"qual": qual, "unknown": []}
    names = list(dict.fromkeys(p.strip() for p in parameter.split(",") if p.strip()))
    return {"qual": [n + "_qual" for n in names if n + "_qual" in qual],
            "unknown": [n for n in names if n + "_qual" not in qual]}


def depth_tolerance(grid, depths):
    """Half the median bin spacing of the depth grid (or of the measured depths if there is no grid), plus 1e-6."""
    for values in (grid, depths):
        if values is None:
            continue
        values = np.unique(np.asarray(values, dtype=float)[np.isfinite(np.asarray(values, dtype=float))])
        if len(values) > 1:
            return float(np.median(np.diff(values))) / 2 + 1e-6
    return 1e-6


def parse_event_depths(spec, depths, log, line, tol):
    """Map an events depth spec (a value, a range "10-20" or a comma separated mix of both) to boolean masks over
    depths. Returns a list of (mask, low, high), one per item, or None if the spec cannot be parsed."""
    items = []
    for item in [i.strip() for i in spec.split(",") if i.strip()]:
        match = re.fullmatch(r"(-?\d+(?:\.\d*)?)\s*-\s*(-?\d+(?:\.\d*)?)", item)
        try:
            if match:
                low, high = float(match.group(1)), float(match.group(2))
                if low > high:
                    raise ValueError
                low, high = low - tol, high + tol
            else:
                value = float(item)
                low, high = value - tol, value + tol
        except ValueError:
            log.warning("Unable to parse depth '{}' in events line {}, event skipped.".format(spec, line), indent=4)
            return None
        mask = (depths >= low) & (depths <= high)
        if not mask.any():
            finite = depths[np.isfinite(depths)]
            available = "{:.2f} to {:.2f} m".format(finite.min(), finite.max()) if len(finite) else "none"
            log.warning("Depth {} in events line {} not present in the data (depths in event window: {}).".format(
                item, line, available), indent=4)
        items.append((mask, low, high))
    if not items:
        log.warning("Unable to parse depth '{}' in events line {}, event skipped.".format(spec, line), indent=4)
        return None
    return items


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