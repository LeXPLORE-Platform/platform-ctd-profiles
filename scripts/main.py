# -*- coding: utf-8 -*-
import os
import sys
import yaml
from ctd import ctd, copyFiles


def main(reprocess=False):
    lake_info = {"lat": 46.49, "alt": 372.1}

    with open("scripts/input_python.yaml", "r") as f:
        directories = yaml.load(f, Loader=yaml.FullLoader)

    for directory in directories.values():
        if not os.path.exists(directory):
            os.makedirs(directory)

    if reprocess:
        files = os.listdir(directories["Level0_dir"])
        files = [os.path.join(directories["Level0_dir"], f) for f in files]
    else:
        files = copyFiles(directories["Level0_dir"], directories["raw"])

    files.sort()
    print("Processing {} files...".format(len(files)))

    for file in files:
        CTD = ctd()
        valid = CTD.read_raw_data(file)
        if valid:
            CTD.extract_profile()
            CTD.quality_assurance()
            if CTD.derive_variables(lake_info["lat"], lake_info["alt"]):
                CTD.quality_assurance()
                CTD.to_netcdf(directories["Level1_dir"], "L1")
                CTD.mask_data()
                CTD.profile_to_timeseries_grid()
                CTD.to_netcdf(directories["Level2_dir"], "L2", output_period="monthly", grid=True)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "reprocess":
        main(reprocess=True)
    else:
        main()
