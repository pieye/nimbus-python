<img src="./assets/PIEYE_Logo_RGB_POS.png" align="right"
     title="pieye logo" width="184" height="55">

# nimbus-python
Python bindings for nimbus

# Getting started

The following snippet connects to the raspberry and gets the image data.

```python
import nimbusPython
cli = nimbusPython.RawStreamClient("192.168.0.69")
cli.connect()
header, (ampl, dist, x, y, z, conf) = cli.getImage()
cli.disconnect()
```

# Installation
```
pip install nimbus-python
```

# Prerequisites
Download the current image from https://cloud.pieye.org/index.php/s/c2QSa6P4wBtSJ4K which contains nimbus-userland and all necessary linux drivers.

# Authors
Markus Proeller

See also the list of contributors who participated in this project.

# License
This project is licensed under the GPLv3 License - see the LICENSE file for details

# 3rd party libraries
We use the following 3rd party libraries:
 
- websockets (BSD 3-Clause "New" or "Revised" License), see https://github.com/aaugustin/websockets
