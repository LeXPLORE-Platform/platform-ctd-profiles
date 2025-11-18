# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import argparse
from instruments import CTD
from general.functions import logger, files_in_directory
from functions import retrieve_new_files

def main(server=False, logs=False):
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if logs:
        log = logger(os.path.join(repo, "logs/ctd"))
    else:
        log = logger()
    log.initialise("Processing LéXPLORE CTD data")
    directories = {f: os.path.join(repo, "data", f) for f in ["Level0", "Level1", "Level2"]}
    for directory in directories:
        os.makedirs(directories[directory], exist_ok=True)
    edited_files = []

    log.begin_stage("Collecting inputs")
    if server:
        log.info("Processing files from sftp server")
        if not os.path.exists(os.path.join(repo, "creds.json")):
            raise ValueError("Credential file required to retrieve live data from the fstp server.")
        with open(os.path.join(repo, "creds.json"), 'r') as f:
            creds = json.load(f)
        files = retrieve_new_files(directories["Level0"], creds, server_location="data/CTD_SST", filetype=".TOB")
        edited_files = edited_files + files
    else:
        files = files_in_directory(directories["Level0"])
        files.sort()
        log.info("Reprocessing complete dataset from {}".format(directories["Level0"]))
    log.end_stage()

    log.begin_stage("Processing data...")
    for file in files:
        sensor = CTD()
        if sensor.read_data(file):
            sensor.extract_profile()
            sensor.quality_assurance(file_path=os.path.join(repo, "notes", "quality_assurance.json"))
            if sensor.derive_variables(46.49, 372.1):
                sensor.quality_assurance(file_path=os.path.join(repo, "notes", "quality_assurance.json"))
                edited_files.extend(sensor.export(directories["Level1"], "L1_CTD", output_period="file"))
                sensor.mask_data()
                sensor.profile_to_timeseries_grid()
                edited_files.extend(sensor.export(directories["Level2"], "L2_CTD", output_period="monthly", grid=True))
    log.end_stage()

    return edited_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', '-s', help="Collect and process new files from FTP server", action='store_true')
    parser.add_argument('--logs', '-l', help="Write logs to file", action='store_true')
    args = vars(parser.parse_args())
    main(server=args["server"], logs=args["logs"])
