<img src="./assets/PIEYE_Logo_RGB_POS.png" align="right"
     title="pieye logo" width="184" height="55">

# nimbus-python
Python bindings for nimbus. These bindings are ment for a remote connection (raspberry to a desktop machine).

# Quick start

The following snippet connects to the raspberry and gets image data.

```python
from nimbusPython import NimbusClient
cli = NimbusClient.NimbusClient("192.168.0.69")
header, (ampl, radial, x, y, z, conf) = cli.getImage(invalidAsNan=True)
```

# Installation

nimbus-python uses websockets, which requires python 3.6 or higher!
```
pip install nimbus-python
```

# Prerequisites
Download the current image from https://cloud.pieye.org/index.php/s/c2QSa6P4wBtSJ4K which contains nimbus-userland and all necessary linux drivers.

# Getting image data

The following snippet connects to the raspberry and gets the image data.

```python
from nimbusPython import NimbusClient
cli = NimbusClient.NimbusClient("192.168.0.69")
header, (ampl, radial, x, y, z, conf) = cli.getImage(invalidAsNan=True)
```

The matrices x,y,z represent a point cloud. Those can be visualized by:
- mayavi (https://docs.enthought.com/mayavi/mayavi/auto/mlab_helper_functions.html#mayavi.mlab.points3d),
- matplotlib (https://matplotlib.org/mpl_toolkits/mplot3d/tutorial.html#scatter-plots)
- any other plotting library

The matrices have the following meaning

| Matrix  |  Explanation  |
| ------- | ------------- |
| ampl    | signal strength of each pixel |
| radial  | radial distance of each pixel to the camera center |
| x,y,z   | 3D Point cloud |
| conf    | confidence information of each pixel (valid, underexposured, saturated, asymmetric) |

You can change the exposure of the Nimbus 3D. By default,  auto exposure with HDR is activated. If there is a lot of movement, it may be necessary to disable HDR and use the normal auto exposure. However, it is also possible to set the exposure time manually with and without HDR.The following snippet contains the possible configurations.

```python
# automatic exposure 
cli.setExposureMode(AUTO_HDR)
cli.setExposureMode(AUTO)
cli.setAmplitude(1000)  #<-- to change the desired amplitude (0 - ~5000)

# manual exposure 
cli.setExposureMode(MANUAL_HDR)
cli.setExposureMode(MANUAL)
cli.setExposure(5000)  #<-- to change the exposure time (0 - 65535)
```

If you are interested in the amount of valid, under exposured etc. pixels, you can use the following snippet as an example.

```python
header, (ampl, radial, x, y, z, conf) = cli.getImage(invalidAsNan=True)
numUnderExposured = len(conf[conf==NimbusClient.ConfUnderExposured])
numOverExposured = len(conf[conf==NimbusClient.ConfOverExposured])
numAsymmetric = len(conf[conf==NimbusClient.ConfAsymmetric])
numValid = len(conf[conf==NimbusClient.ConfValid])
```

Based on this information you probably want to change the illumination time (increase the illumination in case of many underexposured pixels):

```python
rv, data = cli.getExposure()
if rv == 0:
    # increase illumination time by 10%
    newExposure = int(data["exposure"] + data["exposure"]*0.1)
    rv = cli.setExposure(newExposure)
    assert rv==0
```

The illumination time can have any value between 0 and 65535.

Similarily if you want to decrease the number of frames taken by the camera, you can set a framerate value (0 means no pause at end of frame, 65535 means maximum pause at end of frame)
```python
# fast acquisition
rv = cli.setFramerate(0)
assert rv==0
# slow acquisition
rv = cli.setFramerate(65535)
assert rv==0
```

# Authors
Markus Proeller

See also the list of contributors who participated in this project.

# License
This project is licensed under the GPLv3 License - see the LICENSE file for details

# 3rd party libraries
We use the following 3rd party libraries:
 
- websockets (BSD 3-Clause "New" or "Revised" License), see https://github.com/aaugustin/websockets
- requests (Apache V2.0 License), see https://github.com/psf/requests
