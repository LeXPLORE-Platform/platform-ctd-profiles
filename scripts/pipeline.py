# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import argparse
import requests
from download_remote_data import download_remote_data
from upload_remote_data import upload_files, sync_files
from main import main

def pipeline(download=False, process=False, reprocess=False, logs=False, upload=False, uploadfiles=False, datalakes=False):
    if download:
        print("Download sync with remote bucket")
        download_remote_data(warning=False, delete=True)

    failed = False
    if process:
        try:
            edited_files = main(not reprocess, logs)
        except Exception as e:
            print("Processing failed")
            failed = True
            if reprocess:
                raise

    if upload or (uploadfiles and failed):
        print("Upload sync with remote bucket")
        sync_files(warning=False, delete=True)
    elif uploadfiles:
        print("Uploading edited files to remote bucket")
        upload_files(edited_files)

    if datalakes:
        for index, datalakes_id in enumerate(datalakes):
            requests.get("https://api.datalakes-eawag.ch/update/{}".format(datalakes_id))
            time.sleep(30)

    if failed:
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', '-d', help="Download sync with remote bucket", action='store_true')
    parser.add_argument('--process', '-p', help="Run processing code", action='store_true')
    parser.add_argument('--reprocess', '-r', help="Reprocess complete dataset", action='store_true')
    parser.add_argument('--logs', '-l', help="Write logs to file", action='store_true')
    parser.add_argument('--upload', '-u', help="Upload sync with remote bucket", action='store_true')
    parser.add_argument('--uploadfiles', '-uf', help="Upload edited files to remote bucket", action='store_true')
    parser.add_argument('--datalakes', '-dl', type=lambda s: list(map(int, s.split(','))) if s else False, nargs="?", const=False, default=False, help="Datalakes ID's to update, or False if not provided.")
    args = vars(parser.parse_args())
    pipeline(download=args["download"], process=args["process"], reprocess=args["reprocess"], logs=args["logs"], upload=args["upload"], uploadfiles=args["uploadfiles"], datalakes=args["datalakes"])