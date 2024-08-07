# Project Data

The data for this project is stored remotely in the object store: https://eawag-data.s3.eu-central-1.amazonaws.com

In order to work with the data you need to sync the remote data folder with this "local" data folder.
You can use the script `scripts/download_remote_data.py` as follows to download the data:

**The AWS CLI is required to sync the remote data store with your local machine, instructions on how to install can be
found [here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).**

```console
python scripts/download_remote_data.py -d
```

Run `python scripts/download_remote_data.py -h` for details on optional arguments.
