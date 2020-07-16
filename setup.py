from setuptools import setup, find_packages
import os

if "GITHUB_REF" in os.environ:
      version = os.environ["GITHUB_REF"].split("/")[-1]
else:
      version = "0.0.1"

setup(name='nimbus-python',
      version=version,
      description='python bindings for nimbus 3D camera',
      url='https://github.com/pieye/nimbus-python',
      author='Markus Proeller',
      author_email='markus.proeller@pieye.org',
      license='GPLv3',
      include_package_data=True,
      install_requires=[
        "websockets", "numpy", "requests"
      ],
      packages=find_packages(),
      zip_safe=False)
