# -*- coding: utf-8 -*-
"""
Created on Mon Aug 20 21:07:40 2018

@author: Markus
"""
import numpy
import base64
import struct
import requests
import json
import asyncio
import websockets
import threading
import traceback
import socket

NimbusImageRaw = 1
NimbusImageDist = 2
NimbusImageAmpl = 4
NimbusImageX = 8
NimbusImageY = 16
NimbusImageZ = 32
NimbusImageConf = 64

HeaderImgType          = 2
HeaderROIWidth         = 3
HeaderROIHeight        = 4
HeaderROITop           = 5
HeaderROILeft          = 6
HeaderNumSequences     = 7
HeaderFPS              = 8
HeaderTemperature      = 9
HeaderReconfigCnt      = 11
HeaderMetaFrameCounter = 12
HeaderSequenceRestarts = 13
ConfLong           = 0
ConfUnderExposured = 1
ConfOverExposured  = 2
ConfAsymmetric     = 3
ConfShort          = 4

MANUAL      = 0
MANUAL_HDR  = 1
AUTO        = 2
AUTO_HDR    = 3

MANUAL_HDR_FACTOR = 0.3

class NImage:
    @staticmethod
    def create(buf):
        version, headerSize = struct.unpack("<ff", buf[:8])
        headerSize = int(headerSize)
        header = numpy.frombuffer(buf[:headerSize],dtype=numpy.float32)
        imgType = int(header[HeaderImgType])
        width = int(header[HeaderROIWidth])
        height = int(header[HeaderROIHeight])
        numSeqs = int(header[HeaderNumSequences])


        if imgType == NimbusImageRaw:
            arr = numpy.frombuffer(buf, dtype=numpy.uint16)
            arr = arr.reshape((numSeqs, height, width))
        else:
            imgSize = height*width*2
            confSize = height*width*1

            amplStart = headerSize
            if imgType & NimbusImageAmpl:
                amplStop  = amplStart+imgSize
                ampl = numpy.frombuffer(buf[amplStart:amplStop], dtype=numpy.uint16).reshape((height, width))
            else:
                amplStop = amplStart
                ampl = numpy.array([], dtype=numpy.uint16)

            radialStart = amplStop
            if imgType & NimbusImageDist:
                radialStop  = amplStop+imgSize
                radial = numpy.frombuffer(buf[radialStart:radialStop], dtype=numpy.uint16).reshape((height, width))
            else:
                radialStop  = radialStart
                radial = numpy.array([], dtype=numpy.uint16)

            confStart = radialStop
            if imgType & NimbusImageConf:
                confStop = confStart + confSize
                conf = numpy.frombuffer(buf[confStart:confStop], dtype=numpy.uint8).reshape((height, width))
            else:
                confStop = confStart
                conf = numpy.array([], dtype=numpy.uint8)

            xStart = confStop
            if imgType & NimbusImageX:
                xStop = xStart + imgSize
                x = numpy.frombuffer(buf[xStart:xStop], dtype=numpy.int16).reshape((height, width))
            else:
                xStop = xStart
                x = numpy.array([], dtype=numpy.int16)

            yStart = xStop
            if imgType & NimbusImageY:
                yStop = yStart + imgSize
                y = numpy.frombuffer(buf[yStart:yStop], dtype=numpy.int16).reshape((height, width))
            else:
                yStop  = yStart
                y = numpy.array([], dtype=numpy.int16)

            zStart = yStop
            if imgType & NimbusImageZ:
                zStop = zStart + imgSize
                z = numpy.frombuffer(buf[zStart:zStop], dtype=numpy.int16).reshape((height, width))
            else:
                zStop = zStart
                z = numpy.array([], dtype=numpy.int16)

            arr = (ampl, radial, x, y, z, conf)

        return header, arr


class NimbusClient:
    
    def __init__(self, addr, continuousTrig=False, port=8080, jsonPort=8383, rcvTimeout=3, reconnectIntents=5, pingTimeout=3, imgBufSize=10):
        self._addr = addr
        self._streamPort = port
        self._streamURL = "ws://%s:%d/stream"%(addr, port)
        self._jsonPort = jsonPort

        self._rcvTimeout = rcvTimeout
        self._pingTimeout = pingTimeout
        self._reconnectIntents = reconnectIntents

        self._imgBufSize = imgBufSize
        self._listenStarted = False
        self._listenEnded = False
        self._connected = False
        self._threadUpdate = threading.Event()
        self._disconnectMe = False

        self._asyncioLoop = asyncio.new_event_loop()
        self._imageQueue = None

        c_ = 299792458
        fmod = 11.78e6
        self._UR = c_ / (2*fmod)

        self._acqThread = None
        self.connect()

        rv, spread = self.getSpreadFactorXYZ()
        if rv != 0:
            raise RuntimeError("error getting unit vector spread factor")
        rv, self._ux = self.getUnitVectorX()
        if rv != 0:
            raise RuntimeError("error getting unit vector x")
        rv, self._uy = self.getUnitVectorY()
        if rv != 0:
            raise RuntimeError("error getting unit vector y")
        rv, self._uz = self.getUnitVectorZ()
        if rv != 0:
            raise RuntimeError("error getting unit vector z")
        self._ux = self._ux.astype(float) / spread
        self._uy = self._uy.astype(float) / spread
        self._uz = self._uz.astype(float) / spread

    def __del__(self):
        self.disconnect()

    async def listenForever(self):
        self._imageQueue = asyncio.Queue()
        self._listenStarted = True
        sleepTime = 0.1
        intent = 0
        while intent < self._reconnectIntents:
        # outer loop restarted every time the connection fails
            self._connected = False
            if self._disconnectMe == True:
                break
            try:
                async with websockets.connect(self._streamURL) as ws:
                    self._connected = True
                    self._threadUpdate.set()
                    while True:
                        if self._disconnectMe == True:
                            break
                    # listener loop
                        try:
                            reply = await asyncio.wait_for(ws.recv(), timeout=self._rcvTimeout)
                            if self._imageQueue.qsize() >= self._imgBufSize:
                                #remove old images from queue
                                await self._imageQueue.get()

                            await self._imageQueue.put(reply)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                            try:
                                pong = await ws.ping()
                                await asyncio.wait_for(pong, timeout=self._pingTimeout)
                                continue
                            except:
                                break  # inner loop
                        # do stuff with reply object
            except socket.gaierror:
                # log something
                continue
            except ConnectionRefusedError:
                # log something else
                continue
            except TimeoutError:
                break
            except:
                self._threadUpdate.set()
                raise
            intent+=1
            self._connected = False
            await asyncio.sleep(sleepTime)
        self._connected = False
        self._listenEnded = True
        self._threadUpdate.set()

    async def _pollQueue(self):
        try:
            image = await asyncio.wait_for(self._imageQueue.get(), timeout=self._rcvTimeout)
            image = NImage.create(image)
        except:
            print('The coroutine raised an exception:\n%s'%traceback.format_exc())
            image = None
        return image

    def _listenerThread(self):
        task = self._asyncioLoop.create_task(self.listenForever())
        self._asyncioLoop.run_until_complete(task)

    def _setJSONParameter(self, component, paramID, arg):
        url = "http://%s:%d/jsonrpc"%(self._addr, self._jsonPort)
        headers = {'content-type': 'application/json'}
        
        if type(arg) == type([]):
            args = arg
        else:
            args = [arg]
    
        payload = {
            "method": "setParameter",
            "params": {"component": component, "ID":paramID, "param":args},
            "jsonrpc": "2.0",
            "id": 0,
        }
        response = requests.post(
            url, data=json.dumps(payload), headers=headers).json()
    
        assert response['id'] == 0
        assert response["jsonrpc"] == "2.0"
        return response['result']
    
    def _getJSONParameter(self, component, paramID, args):
        url = "http://%s:%d/jsonrpc"%(self._addr, self._jsonPort)
        headers = {'content-type': 'application/json'}
        
        if type(args) != type([]):
            args = [args]
    
        # Example echo method
        payload = {
            "method": "getParameter",
            "params": {"component": component, "ID":paramID, "param":args},
            "jsonrpc": "2.0",
            "id": 0,
        }
        response = requests.post(
            url, data=json.dumps(payload), headers=headers).json()


        assert response['id'] == 0
        assert response["jsonrpc"] == "2.0"
        return response['result']

    def connect(self):
        self._acqThread = threading.Thread(target=self._listenerThread)
        self._acqThread.start()
        self._threadUpdate.wait()
        if self._connected == False:
            raise RuntimeError("could not connect to %s"%self._addr)

    def disconnect(self):
        self._disconnectMe = True
        if self._acqThread != None:
            self._acqThread.join()
            self._acqThread = None

    def getImage(self, invalidAsNan=True):
        image = None
        future = asyncio.run_coroutine_threadsafe(self._pollQueue(), self._asyncioLoop)
        try:
            image = future.result(self._rcvTimeout*2)
        except asyncio.TimeoutError:
            print('The coroutine took too long, cancelling the task...')
            future.cancel()
        except:
            print('The coroutine raised an exception:\n%s'%traceback.format_exc())

        if image != None:
            header, data = image
            imgType = int(header[HeaderImgType])
            if imgType != NimbusImageRaw:
                (ampl, radial, x, y, z, conf) = data
                ampl = ampl.astype(float)
                radial = radial.astype(float)/65535*self._UR
                if invalidAsNan:
                    radial[conf==ConfUnderExposured] = numpy.NAN
                    radial[conf==ConfOverExposured] = numpy.NAN
                    radial[conf==ConfAsymmetric] = numpy.NAN
                if imgType & NimbusImageX == 0:
                    x = radial*self._ux
                if imgType & NimbusImageY == 0:
                    y = radial*self._uy
                if imgType & NimbusImageZ == 0:
                    z = radial*self._uz
                return header, (ampl, radial, x, y, z, conf)
        return image
    
    def enaRawMode(self, ena):
        if ena == True:
            arg = 1
        else:
            arg = 0
        return self._setJSONParameter("preprocessing", 0, arg)
    
    def getUserlandVersion(self):
        result = self._getJSONParameter("preprocessing", 1, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = result["result"]
        return data

    def setFramerate(self, framerate):
        result = self._getJSONParameter("nimbusRaw", 0, None)
        rv = result["success"]
        if rv == 0:
            seqs = result["result"]
            seqs[-1]["framerate"] = int(framerate)
            rv = self._setJSONParameter("nimbusRaw", 0, seqs)
        return rv

    def setExposure(self, exposure, framerate=0):
        result = self._getJSONParameter("nimbusRaw", 0, None)
        rv = result["success"]
        if rv == 0:
            seqs = result["result"]
            for i in range(len(seqs)):
                #Short Exposure if more then 6 sequences --> HDR
                if i < 6:               
                    seqs[i]["exposure"] = int(exposure)
                else:
                    seqs[i]["exposure"] = int(exposure*MANUAL_HDR_FACTOR)
            seqs[-1]["framerate"] = int(framerate)
        rv = self._setJSONParameter("nimbusRaw", 0, seqs)
        return rv
            
    def getExposure(self):
        result = self._getJSONParameter("nimbusRaw", 0, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = result["result"][-1]
        return rv, data

    def getIdent(self):
        result = self._getJSONParameter("nimbusRaw", 8, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = base64.b64decode(result["result"])
            data = struct.unpack("BBBBBB", data)
            data = ":".join(["%02X"%x for x in data])
        return rv, data

    def getUnitVectorX(self):
        result = self._getJSONParameter("nimbusRaw", 4, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = base64.b64decode(result["result"])
            data = numpy.frombuffer(data, dtype=numpy.int16).reshape(286,352)
        return rv, data

    def getUnitVectorY(self):
        result = self._getJSONParameter("nimbusRaw", 5, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = base64.b64decode(result["result"])
            data = numpy.frombuffer(data, dtype=numpy.int16).reshape(286,352)
        return rv, data

    def getUnitVectorZ(self):
        result = self._getJSONParameter("nimbusRaw", 6, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = base64.b64decode(result["result"])
            data = numpy.frombuffer(data, dtype=numpy.int16).reshape(286,352)
        return rv, data

    def getSpreadFactorXYZ(self):
        result = self._getJSONParameter("nimbusRaw", 7, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = result["result"]
        return rv, data

    def getLog(self):
        result = self._getJSONParameter("logHandler", 0, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = result["result"]
        return rv, data
    
    def setAmplitude(self, ampl):
        rv = self._setJSONParameter("AutoExposure", 2, int(ampl))
        return rv    

    def getAmplitude(self):
        result = self._getJSONParameter("AutoExposure", 2, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = result["result"]
        return rv, data

    def setMaxExposure(self, exposure):
        rv = self._setJSONParameter("AutoExposure", 0, int(exposure))
        return rv    

    def getMaxExposure(self):
        result = self._getJSONParameter("AutoExposure", 0, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = result["result"]
        return rv, data

    def setExposureMode(self, exposure_mode):
        rv = self._setJSONParameter("AutoExposure", 1, int(exposure_mode))
        return rv    

    def getExposureMode(self):
        result = self._getJSONParameter("AutoExposure", 1, None)
        rv = result["success"]
        data = None
        if (rv == 0):
            data = result["result"]
        return rv, data

if __name__ == "__main__":
    cli = NimbusClient("192.168.1.24")
    header, (ampl, radial, x, y, z, conf) = cli.getImage(invalidAsNan=True)
