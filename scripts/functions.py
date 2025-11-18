import os
import json
import math
import ftplib
import numpy as np
import pandas as pd
import seawater as sw
from shutil import copyfile
from envass import qualityassurance
from datetime import datetime, timedelta
from general.functions import logger

def retrieve_new_files(folder, creds, server_location="data", filetype=".csv", remove=False, overwrite=False, log=logger()):
    files = []
    log.info("Connecting to {}.".format(creds["ftp"]), indent=1)
    ftp = ftplib.FTP(creds["ftp"], timeout=100)
    ftp.login(creds["user"], creds["password"])
    server_files = ftp.nlst(server_location)
    local_files = os.listdir(folder)
    for file in server_files:
        file_name = os.path.basename(file)
        if file.endswith(filetype) and (overwrite or file_name not in local_files):
            log.info("Downloading file {}".format(file), indent=2)
            download_file(file, os.path.join(folder, file_name), ftp)
            if remove:
                ftp.delete(file)
            files.append(os.path.join(folder, file_name))
    files.sort()
    return files


def download_file(server, local, ftp):
    with open(local, "wb") as f:
        ftp.retrbinary("RETR " + server, f.write)


def is_number(n):
    try:
        float(n)
    except ValueError:
        return False
    else:
        return True


def check_valid_profile(data, value):
    if np.nanmax(data) > value:
        return True
    else:
        return False


def fixed_grid_resample_guide(data, grid):
    resample = []
    for g in grid:
        for j in range(len(data)):
            if data[j] > g or j >= len(data) - 1:
                resample.append({"index": False})
                break
            elif data[j] <= g < data[j + 1]:
                itp = (g - data[j]) / (data[j + 1] - data[j])
                resample.append({"index": j, "interpolation": itp})
                break
    return resample


def resample(guide, data):
    out = []
    for i in range(len(guide) - 1):
        if not guide[i]["index"]:
            out.append(np.nan)
        else:
            value = ((data[guide[i]["index"] + 1] - data[guide[i]["index"]]) * guide[i]["interpolation"]) + data[
                guide[i]["index"]]
            out.append(value)
    out.append(np.nan)
    return out


def index_of_max(arr):
    return np.argmax(np.array(arr))


def position_in_array(arr, value):
    for i in range(len(arr)):
        if value < arr[i]:
            return i
    return len(arr)


def round_to_days(dt, n):
    day = math.floor(dt.day / n) * n
    if day < 10:
        return "0" + str(day)
    else:
        return str(day)


def advanced_quality_flags(df, json_path="quality_assurance.json"):
    """
        input :
            - df is a dataframe of level 1B where basic check have been performed
            - json path: path for the advanced quality check json file, produced by the jupyter notebook
        output:
            - dictionnary where the dataframe is stored with updated advanced quality checks
        """
    quality_assurance_dict = json.load(open(json_path))
    var_name = quality_assurance_dict.keys()
    advanced_df = df.copy()
    for var in var_name:
        if quality_assurance_dict[var]:
            if var in advanced_df.keys():
                qa = qualityassurance(np.array(df[var]), np.array(df["time"]),
                                      **quality_assurance_dict[var]["advanced"])
                advanced_df[var + "_qual"].values[np.array(qa, dtype=bool)] = 1
    return advanced_df


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


def log(str, indent=0, start=False):
    if start:
        out = "\n" + str + "\n"
        with open("log.txt", "w") as file:
            file.write(out + "\n")
    else:
        out = datetime.now().strftime("%H:%M:%S.%f") + (" " * 3 * (indent + 1)) + str
        with open("log.txt", "a") as file:
            file.write(out + "\n")
    print(out)


def error(str):
    out = datetime.now().strftime("%H:%M:%S.%f") + "   ERROR: " + str
    with open("log.txt", "a") as file:
        file.write(out + "\n")
    raise ValueError(str)


def find_closest_index(arr, value):
    return min(range(len(arr)), key=lambda i: abs(arr[i] - value))


def is_number(n):
    try:
        float(n)
    except ValueError:
        return False
    else:
        return True


def isnt_number(n):
    try:
        float(n)
    except ValueError:
        return True
    else:
        return False


def first_centered_differences(x, y, fill=False):
    if x.size != y.size:
        log("first-centered differences: vectors do not have the same size")
    dy = np.full(x.size, np.nan)
    iif = np.where((np.isfinite(x)) & (np.isfinite(y)))[0]
    if iif.size == 0:
        return dy
    x0 = x[iif]
    y0 = y[iif]
    dy0 = np.full(x0.size, np.nan)
    # calculates differences
    dy0[0] = (y0[1] - y0[0]) / (x0[1] - x0[0])
    dy0[-1] = (y0[-1] - y0[-2]) / (x0[-1] - x0[-2])
    dy0[1:-1] = (y0[2:] - y0[0:-2]) / (x0[2:] - x0[0:-2])

    dy[iif] = dy0

    if fill:
        dy[0:iif[0]] = dy[iif[0]]
        dy[iif[-1] + 1:] = dy[iif[-1]]
    return dy


def default_salinity_temperature(temperature):
    return 1.8626 - 0.052908 * temperature + 0.00093057 * temperature ** 2 - 6.78e-6 * temperature ** 3


def salinity(Temp, Cond, y_cond, temperature_func=default_salinity_temperature):
    ft = temperature_func(Temp)
    cond20 = ft * Cond * 1000
    salin = y_cond * cond20
    return salin


def density(temperature, salinity):
    rho = 1e3 * (
            0.9998395 + 6.7914e-5 * temperature - 9.0894e-6 * temperature ** 2 + 1.0171e-7 * temperature ** 3 -
            1.2846e-9 * temperature ** 4 + 1.1592e-11 * temperature ** 5 - 5.0125e-14 * temperature ** 6 + (
                    8.181e-4 - 3.85e-6 * temperature + 4.96e-8 * temperature ** 2) * salinity)
    return rho


def Gamma_adiabatic(T, S, p, lat=46.):
    alpha = sw.alpha(S, T, p)
    cp = sw.cp(S, T, p)
    Gamma = sw.g(lat) * alpha * (T - 273.15) / cp
    return Gamma


def mask_single_data(data, mask):
    try:
        idx = mask > 0
        data = data.astype(float)
        data[idx] = np.nan
        return data
    except:
        print("Masking failed")
        return data


def potential_temperature(T, S, p, z, lat=46.2):
    iif = np.where(np.isfinite(T) & np.isfinite(S) & np.isfinite(p) & np.isfinite(z))
    PT = np.full(T.size, np.nan)
    T = T[iif]
    p = p[iif]
    z = z[iif]
    S = S[iif]
    pt0 = np.copy(T)
    n = pt0.size
    pt1 = np.full(n, np.nan)
    iterate = True
    j = 0
    while iterate:
        intGamma = np.zeros(n)
        for i in range(1, n):
            Gamma0 = Gamma_adiabatic(pt0, S[i], p, lat)
            intGamma[i] = np.trapz(Gamma0[0:i + 1], x=z[0:i + 1])
        pt1 = T + intGamma
        j += 1
        if j > 100 or np.nanmax(np.abs(pt1 - pt0)) < 1e-3:
            iterate = False
        else:
            pt0 = np.copy(pt1)

    PT[iif] = pt1
    return PT


def potential_temperature_sw(T, S, p, p_ref):
    """
    Calculates potential temperature as per UNESCO 1983 report.
    Parameters
    ----------
    s(p) : array_like
        salinity [psu (PSS-78)]
    t(p) : array_like
        temperature [℃ (ITS-90)]
    p : array_like
        pressure [db].
    pr : array_like
        reference pressure [db], default = 0
    Returns
    -------
    pt : array_like
        potential temperature relative to PR [℃ (ITS-90)]
    """
    return sw.ptmp(s=S, t=T, p=p, pr=p_ref)


def oxygen_saturation(T, S, altitude=372., lat=46.2, units="mgl"):
    # calculates oxygen saturation in mg/l according to Garcia-Benson
    # to be coherent with Hannah
    if units != "mgl" and units != "mll":
        units = "mgl"
    mgL_mlL = 1.42905
    mmHg_mb = 0.750061683
    mmHg_inHg = 25.3970886
    standard_pressure_sea_level = 29.92126
    standard_temperature_sea_level = 15 + 273.15
    gravitational_acceleration = gr = sw.g(lat)
    air_molar_mass = 0.0289644
    universal_gas_constant = 8.31447
    baro = (1. / mmHg_mb) * mmHg_inHg * standard_pressure_sea_level * np.exp(
        (-gravitational_acceleration * air_molar_mass * altitude) / (
                universal_gas_constant * standard_temperature_sea_level))
    u = 10 ** (8.10765 - 1750.286 / (235 + T))
    press_corr = (baro * mmHg_mb - u) / (760 - u)

    Ts = np.log((298.15 - T) / (273.15 + T))
    lnC = 2.00907 + 3.22014 * Ts + 4.0501 * Ts ** 2 + 4.94457 * Ts ** 3 + -0.256847 * Ts ** 4 + 3.88767 * Ts ** 5 - S * (
            0.00624523 + 0.00737614 * Ts + 0.010341 * Ts ** 2 + 0.00817083 * Ts ** 3) - 4.88682e-07 * S ** 2
    O2sat = np.exp(lnC)
    if units == "mll":
        O2sat = O2sat * press_corr
    elif units == "mgl":
        O2sat = O2sat * mgL_mlL * press_corr

    return O2sat


def parse_file(input_file_path, string):
    valid = True
    with open(input_file_path, encoding="latin1", errors='ignore') as f:
        lines = f.readlines()
    for i in range(len(lines)):
        if string in lines[i]:
            break
    if "APHYS_Field" in lines[i - 1]:
        date_format = "%m/%d/%Y %H:%M:%S"
    else:
        date_format = "%d/%m/%Y %H:%M:%S"
    columns = lines[i + 2].replace(";", "").split()
    columns.pop(0)
    columns = rename_duplicates(columns)
    units = lines[i + 3].replace(";", "").replace("[", "").replace("]", "").replace("°", "deg").split()
    skip_rows = i + 5

    n = 0
    while len(lines[i + 5].split()) - 1 > len(columns):
        columns.append(n)
        n = n + 1

    if len(lines) <= skip_rows + 1 or len(columns) < 5:
        valid = False

    return skip_rows, columns, units, valid, date_format


def rename_duplicates(arr):
    out = []
    d = {}

    for i in arr:
        d.setdefault(i, -1)
        d[i] += 1

        if d[i] >= 1:
            out.append('%s%d' % (i, d[i]))
        else:
            out.append(i)
    return out


def check_variable(variable, unit, columns, units):
    if variable in columns:
        for i in range(len(columns)):
            if variable == columns[i]:
                break
        if units[i].lower() in unit.lower():
            return True
        else:
            log("{} needs unit [{}] but has unit [{}]".format(variable, unit, units[i]))
            return False
    else:
        return False


def parse_time(df, variable, name, columns, units, ref_date, date_format):
    if "IntD" in columns and "IntT" in columns:
        try:
            datetime_arr = pd.to_datetime(df["IntD"] + " " + df["IntT"], format=date_format, dayfirst=True)
            try:
                datetime_arr[df[df[0] == "PM"].index] = datetime_arr[df[df[0] == "PM"].index] + timedelta(hours=12)
            except:
                pass
            idx = np.argmin(np.diff(datetime_arr))
            if np.diff(datetime_arr)[idx].astype("float") < 0:
                datetime_arr[idx + 1:] = np.copy(datetime_arr[idx + 1:] + timedelta(hours=12))
            arr = list(datetime_arr.values.astype(float) / 10 ** 9)
            if ref_date and abs(arr[0] - ref_date) > 30 * 24 * 60 * 60:
                arr = list(
                    datetime_arr.values.astype(float) / 10 ** 9)
            return arr
        except:
            log("Datetime file parse failed")
            raise
    elif "IntDT" in columns and "IntDT1" in columns:
        try:
            arr = list(pd.to_datetime(df["IntDT"] + " " + df["IntDT1"], dayfirst=True).values.astype(float) / 10 ** 9)
            if ref_date and abs(arr[0] - ref_date) > 30 * 24 * 60 * 60:
                arr = list(
                    pd.to_datetime(df["IntDT"] + " " + df["IntDT1"], dayfirst=False).values.astype(float) / 10 ** 9)
            return arr
        except:
            log("Datetime file parse failed")
            raise
    elif "IntD" in columns:
        try:
            return [(datetime(1900, 1, 1) + timedelta(days=x)).timestamp() for x in list(df["IntD"])]
        except:
            log("Datetime file parse failed")
            raise
    else:
        return [ref_date] * len(df)


def parse_chl(df, variable, name, columns, units, ref_date, date_format):
    a = np.empty(len(df))
    a[:] = np.nan
    if units == "g/l":
        try:
            log("Changed Chl unit")
            return np.array(df[name] * 1000000, dtype=float)
        except:
            return a
    else:
        return a