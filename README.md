# LéXPLORE CTD

## Project Information

The data is collected within the frame of the [LeXPLORE project](https://wp.unil.ch/lexplore/) on Lake Geneva. 
The data is used and displayed on the [Datalakes website](https://www.datalakes-eawag.ch/).

## Sensors

The CTD is an instrument used to measure the conductivity, temperature, and pressure of the lake water (the D stands for "depth," which is closely related to pressure).

## Installation

- Clone the repository to your local machine using the command:

 `git clone git@github.com:LeXPLORE-Platform/platform-ctd-profiles.git`

- Create the Python environment with [conda](https://conda-forge.org/download/) and activate it:

 `conda env create -f environment.yml`

 `conda activate pipeline`

## Usage

### Process data

`scripts/main.py` processes the CTD profiles in `data/Level0` to Level 1 and Level 2.

- `python scripts/main.py --server` downloads new profiles from the FTP server (requires `creds.json`, see `creds_example.json`) and processes only those.
- `python scripts/main.py` reprocesses every file in `data/Level0`.

Existing Level 1 and Level 2 files are not overwritten. To reprocess the complete dataset (for example after editing
`notes/events.csv` or `notes/quality_assurance.json`), empty `data/Level1` and `data/Level2` first.

Run `python scripts/main.py -h` for details on the input arguments available. `scripts/pipeline.py` wraps `main.py` with
the download and upload steps used operationally (see `entrypoint.sh`).

### Adapt/Extend data processing pipeline

`scripts/main.py` defines the processing steps, and `scripts/instruments.py` contains the `CTD` class with the
methods that process the data. Methods shared with other LéXPLORE datasets are in `scripts/general/functions.py`.
To add a new processing step, add a method to the `CTD` class and call it from `main.py`.

## Data

The data can be found in the folder `data`. The data is structured as follows:

### Data Structure

- **Level 0**: Raw `.TOB` files from the CTD, one file per profile.

- **Level 1**: One NetCDF file per profile, with quality flags added. Quality flag "1" indicates that the data point didn't pass the
quality checks (or is covered by an event, see below) and further investigation is needed, quality flag "0" indicates that no further investigation is needed.
Derived variables (salinity, density, depth, potential temperature, potential density, Thorpe displacements and oxygen saturation) are added.

- **Level 2**: Level 1 data with flagged points set to NaN, interpolated to a fixed vertical grid from 0 to 120 m with a spacing of 0.1 m.
The data is stored in monthly NetCDF files.

## Quality assurance

Quality checks include but are not limited to range validation, data type checking and flagging missing data.
The automatic quality check is controlled by the package [Envass](https://pypi.org/project/envass/). The specific methods implemented for this dataset are listed in `notes/quality_assurance.json`.
Data from before the CTD enters the water and from the upcast is also flagged.

### Events

Maintenance dates, sensor problems and other events not identified by the automatic quality assurance are listed in `notes/events.csv`.
These events are applied to the quality flags (`<variable>_qual = 1`) when the data are processed to Level 1, and the flagged data are
therefore NaN in Level 2. The file is semicolon separated with the columns `start;stop;parameter;depth;comments`:

- `start`, `stop`: UTC, format `YYYYMMDD HH:MM:SS` (inclusive). An empty `stop` means the event is ongoing.
- `parameter`: `All` or a comma separated list of variable names as they appear in the Level 1 files (e.g. `Cond,Turb`).
  Flagging `Temp`, `Cond`, `Press` or `DO_mg` also flags the variables calculated from them:
  - `Temp`, `Cond` → `SALIN`, `rho`, `depth`, `pt`, `prho`, `sat`, `thorpe`
  - `Press` → `depth`, `pt`, `prho`, `sat`, `thorpe`
  - `DO_mg` → `sat`
- `depth`: empty or `All` flags the whole profile within the time window. Otherwise only the points whose calculated depth matches are flagged:
  a single depth (`5`, matching ±0.05 m), a range (`10-20`) or a comma separated list of both (`2.5,10-20`). Depths are in metres.
- `comments`: free text description of the event. If it contains a `;`, put it in double quotes.

Each profile is about 15 minutes long and profiles are a few days apart, so an event has to overlap a profile's time window to flag anything.
Events added for profiles that were already processed only take effect after reprocessing the complete dataset (see [Process data](#process-data)).
Problems in the events file are logged as warnings and do not stop processing.
