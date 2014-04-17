# NikePlus2Runkeeper

This script solves (for me at least) a simple problem. I have a Nike+ SportWatch, that synchronized with NOTHING else. In particular Runkeeper then by proxy MyFitnessPal.

## Requirements

This should be safe for both python >2.6 and 3.

The required libraries should be in your distro repos.
* lxml
* requests

## Overview

The installation should be simple, upload the git directory to a system of your choosing. Enter your details into the config file, then run ./run.py

For me I've add this to my user's cronjob schedule
```
*/15 * * * * cd nikeplus2runkeeper && ./run.py
```
