#!/usr/bin/python3

import os
from pathlib import Path
from threading import Thread
from cameracontrol import CameraControl
from frontend import run_frontend

if __name__ == "__main__":
    os.chdir(Path(__file__).parent)

    camera_contol = CameraControl()
    camera_thread = Thread(target = camera_contol.camera_loop)
    camera_thread.start()
    run_frontend(8000, camera_contol)