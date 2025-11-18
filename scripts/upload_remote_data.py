import os
import sys
import argparse
from subprocess import check_output, Popen, PIPE


def upload_files(files):
    files = list(set(files))
    data_folder, uri = get_uri()
    print("Attempting to upload {} files from {} to {}".format(len(files), data_folder, uri))
    for file in files:
        relative_path = os.path.relpath(file, data_folder)
        process = Popen(["aws", "s3", "cp", file, "{}/{}".format(uri, relative_path)], stdout=PIPE)
        while True:
            output = process.stdout.readline()
            if process.poll() is not None:
                break
            if output:
                print(output.decode('ASCII'))


def sync_files(warning=True, delete=False):
    data_folder, uri = get_uri()
    print("Attempting to sync {} with {}".format(data_folder, uri))
    if warning:
        if delete:
            dry_run = check_output(["aws", "s3", "sync", data_folder, uri, "--dryrun", "--delete"]).decode(
                'ASCII')
        else:
            dry_run = check_output(["aws", "s3", "sync", data_folder, uri, "--dryrun"]).decode('ASCII')
        if len(dry_run) == 0:
            print("{} is up to date.".format(uri))
            return
        print("The following changes will be made:")
        print(dry_run)
        answer = input("Continue? [y/n]")
        if answer.lower() not in ["y", "yes"]:
            return
    if delete:
        process = Popen(["aws", "s3", "sync", data_folder, uri, "--delete"], stdout=PIPE)
    else:
        process = Popen(["aws", "s3", "sync", data_folder, uri], stdout=PIPE)
    while True:
        output = process.stdout.readline()
        if process.poll() is not None:
            break
        if output:
            print(output.decode('ASCII'))
    print("Upload complete.")


def get_uri():
    hosts = ["renkulab.io", "github.com", "gitlab.com", "gitlab.renkulab.io", "gitlab.eawag.ch"]
    folder = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    bucket_file = os.path.join(folder, ".bucket")
    data_folder = os.path.join(folder, "data")
    if not os.path.isfile(bucket_file):
        raise ValueError("{} not found. .bucket file is required to download data".format(bucket_file))
    if not os.path.isdir(data_folder):
        raise ValueError("{} not found. data folder is required to sync data.".format(data_folder))

    remote = str(check_output(["git", "remote", "-v"])).replace(" (push)", "").replace(" (fetch)", "")
    if "git@" in remote:
        remote = str(check_output(["git", "remote", "-v"])).split("git@", 1)[1].split(".git", 1)[0].split(":")
        host = remote[0]
        repository = remote[1]
    elif "https://" in remote:
        remote = str(check_output(["git", "remote", "-v"])).split("https://", 1)[1].split(".git", 1)[0].split("/")
        host = remote[0]
        repository = "/".join(remote[1:])
    else:
        raise ValueError("Unrecognized output from git remote -v: {}".format(remote))

    if host not in hosts:
        raise ValueError("Host {} not recognised. Please select from {} or edit the function to accept your host."
                         .format(host, ", ".join(hosts)))

    with open(bucket_file, 'r') as file:
        bucket = file.read().rstrip()

    bucket_name = bucket.replace("https://", "").split(".")[0]
    uri = "s3://{}/{}/{}/data".format(bucket_name, host, repository)

    return data_folder, uri


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--warning', '-w', help="Remove change warning for automation.", action='store_false')
    parser.add_argument('--delete', '-d', help="Delete files for full sync.", action='store_true')
    args = vars(parser.parse_args())
    sync_files(warning=args["warning"], delete=args["delete"])
