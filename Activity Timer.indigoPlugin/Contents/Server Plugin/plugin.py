#! /usr/bin/env python
# -*- coding: utf-8 -*-
###############################################################################
# http://www.indigodomo.com

import indigo
import time
from datetime import datetime
from ghpu import GitHubPluginUpdater

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

###############################################################################
# globals

k_commonTrueStates = ['true', 'on', 'open', 'up', 'yes', 'active', 'unlocked', '1']

k_stateImages = {
    'SensorOff':    indigo.kStateImageSel.SensorOff,
    'TimerOff':     indigo.kStateImageSel.TimerOff,
    'SensorOn':     indigo.kStateImageSel.SensorOn,
    'TimerOn':      indigo.kStateImageSel.TimerOn,
    }

k_deviceKeys = (
    ('device1', 'state1'),
    ('device2', 'state2'),
    ('device3', 'state3'),
    ('device4', 'state4'),
    ('device5', 'state5'),
    )

k_variableKeys = (
    'variable1',
    'variable2',
    'variable3',
    'variable4',
    'variable5',
    )

k_updateCheckHours = 24

################################################################################
class Plugin(indigo.PluginBase):
    #-------------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.updater = GitHubPluginUpdater(self)

    def __del__(self):
        indigo.PluginBase.__del__(self)

    #-------------------------------------------------------------------------------
    # Start, Stop and Config changes
    #-------------------------------------------------------------------------------
    def startup(self):
        self.debug          = self.pluginPrefs.get('showDebugInfo',False)
        self.logger.debug("startup")
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.nextCheck      = self.pluginPrefs.get('nextUpdateCheck',0)

        self.showTimer      = self.pluginPrefs.get('showTimer',False)
        self.tickTime       = time.time()
        self.deviceDict     = dict()

        indigo.devices.subscribeToChanges()
        indigo.variables.subscribeToChanges()

    #-------------------------------------------------------------------------------
    def shutdown(self):
        self.logger.debug("shutdown")
        self.pluginPrefs['showDebugInfo'] = self.debug
        self.pluginPrefs['nextUpdateCheck'] = self.nextCheck

    #-------------------------------------------------------------------------------
    def validatePrefsConfigUi(self, valuesDict):
        self.logger.debug("validatePrefsConfigUi")
        errorsDict = indigo.Dict()

        if len(errorsDict) > 0:
            self.logger.debug('validate prefs config error: \n{}'.format(errorsDict))
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug("closedPrefsConfigUi")
        if not userCancelled:
            self.debug = valuesDict.get('showDebugInfo',False)
            self.showTimer = valuesDict.get('showTimer',False)
            if self.debug:
                self.logger.debug("Debug logging enabled")

    #-------------------------------------------------------------------------------
    def runConcurrentThread(self):
        try:
            while True:
                self.tickTime = time.time()
                for id, activity in self.deviceDict.iteritems():
                    activity.tick()
                if self.tickTime > self.nextCheck:
                    self.checkForUpdates()
                    self.nextCheck = self.tickTime + k_updateCheckHours*60*60
                self.sleep(self.tickTime + 1 - time.time())
        except self.StopThread:
            pass    # Optionally catch the StopThread exception and do any needed cleanup.

    #-------------------------------------------------------------------------------
    # Device Methods
    #-------------------------------------------------------------------------------
    def deviceStartComm(self, dev):
        self.logger.debug("deviceStartComm: "+dev.name)
        if dev.version != self.pluginVersion:
            self.updateDeviceVersion(dev)
        if dev.configured:
            if dev.deviceTypeId == 'activityTimer':
                self.deviceDict[dev.id] = ActivityTimer(dev, self)
            elif dev.deviceTypeId == 'persistenceTimer':
                self.deviceDict[dev.id] = PersistenceTimer(dev, self)

    #-------------------------------------------------------------------------------
    def deviceStopComm(self, dev):
        self.logger.debug("deviceStopComm: "+dev.name)
        if dev.id in self.deviceDict:
            del self.deviceDict[dev.id]

    #-------------------------------------------------------------------------------
    def validateDeviceConfigUi(self, valuesDict, typeId, devId, runtime=False):
        self.logger.debug("validateDeviceConfigUi: " + typeId)
        errorsDict = indigo.Dict()

        if typeId == 'activityTimer':
            for devKey, stateKey in k_deviceKeys:
                if zint(valuesDict.get(devKey,'')) and not valuesDict.get(stateKey,''):
                    errorsDict[stateKey] = "Required"
            requiredIntegers = ['resetCycles','countThreshold','offCycles']

        elif typeId == 'persistenceTimer':
            requiredIntegers = ['onCycles','offCycles']
            if valuesDict.get('trackEntity','dev') == 'dev':
                keys = k_deviceKeys[0]
            else:
                keys = [k_variableKeys[0]]
            for key in keys:
                if not valuesDict.get(key,''):
                    errorsDict[key] = "Required"

        for key in requiredIntegers:
            if not zint(valuesDict.get(key,'')) > 0:
                errorsDict[key] = "Must be a positive integer"

        if len(errorsDict) > 0:
            self.logger.debug('validate device config error: \n{}'.format(errorsDict))
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def updateDeviceVersion(self, dev):
        theProps = dev.pluginProps
        # update states
        dev.stateListOrDisplayStateIdChanged()
        # check for props

        # push to server
        theProps["version"] = self.pluginVersion
        dev.replacePluginPropsOnServer(theProps)

    #-------------------------------------------------------------------------------
    def deviceUpdated(self, oldDev, newDev):

        # device belongs to plugin
        if newDev.pluginId == self.pluginId or oldDev.pluginId == self.pluginId:
            indigo.PluginBase.deviceUpdated(self, oldDev, newDev)

        else:
            for id, activity in self.deviceDict.items():
                activity.devChanged(oldDev, newDev)

    #-------------------------------------------------------------------------------
    # Variable Methods
    #-------------------------------------------------------------------------------
    def variableUpdated(self, oldVar, newVar):
        for id, activity in self.deviceDict.items():
            activity.varChanged(oldVar, newVar)


    #-------------------------------------------------------------------------------
    # Action Methods
    #-------------------------------------------------------------------------------
    def activityStart(self, action):
        if action.deviceId in self.deviceDict:
            self.deviceDict[action.deviceId].start()
        else:
            self.logger.error('device id "%s" not available' % action.deviceId)

    #-------------------------------------------------------------------------------
    def activityStop(self, action):
        if action.deviceId in self.deviceDict:
            self.deviceDict[action.deviceId].stop()
        else:
            self.logger.error('device id "%s" not available' % action.deviceId)

    #-------------------------------------------------------------------------------
    # Menu Methods
    #-------------------------------------------------------------------------------
    def checkForUpdates(self):
        self.updater.checkForUpdate()

    #-------------------------------------------------------------------------------
    def updatePlugin(self):
        self.updater.update()

    #-------------------------------------------------------------------------------
    def forceUpdate(self):
        self.updater.update(currentVersion='0.0.0')

    #-------------------------------------------------------------------------------
    def toggleDebug(self):
        if self.debug:
            self.logger.debug("Debug logging disabled")
            self.debug = False
        else:
            self.debug = True
            self.logger.debug("Debug logging enabled")

    #-------------------------------------------------------------------------------
    # Callbacks
    #-------------------------------------------------------------------------------
    def getDeviceList(self, filter='', valuesDict=dict(), typeId='', targetId=0):
        devList = list()
        excludeList  = [dev.id for dev in indigo.devices.iter(filter='self')]
        for dev in indigo.devices.iter():
            if not dev.id in excludeList:
                devList.append((dev.id, dev.name))
        devList.append((0,"- none -"))
        return devList

    #-------------------------------------------------------------------------------
    def getStateList(self, filter=None, valuesDict=dict(), typeId='', targetId=0):
        stateList = list()
        devId = zint(valuesDict.get(filter,''))
        if devId:
            for state in indigo.devices[devId].states:
                stateList.append((state,state))
        return stateList

    #-------------------------------------------------------------------------------
    def getVariableList(self, filter='', valuesDict=dict(), typeId='', targetId=0):
        varList = list()
        for var in indigo.variables.iter():
            varList.append((var.id, var.name))
        varList.append((0,"- none -"))
        return varList

    #-------------------------------------------------------------------------------
    def loadStates(self, valuesDict=None, typeId='', targetId=0):
        pass

################################################################################
# Classes
################################################################################
class BaseTimer(object):

    #-------------------------------------------------------------------------------
    def __init__(self, instance, plugin):
        self.dev        = instance
        self.id         = instance.id
        self.name       = instance.name
        self.states     = instance.states

        self.plugin     = plugin
        self.logger     = plugin.logger

        self.reverse    = instance.pluginProps.get('reverseBoolean',False)
        self.stateImg   = None

        self.deviceStateDict = dict()
        for deviceKey, stateKey in k_deviceKeys:
            if zint(instance.pluginProps.get(deviceKey,'')):
                self.deviceStateDict[int(instance.pluginProps[deviceKey])] = instance.pluginProps[stateKey]

        self.variableList = list()
        for variableKey in k_variableKeys:
            if zint(instance.pluginProps.get(variableKey,'')):
                self.variableList.append(int(instance.pluginProps[variableKey]))

    #-------------------------------------------------------------------------------
    def saveStates(self):
        newStates = list()
        for key, value in self.states.iteritems():
            if self.states[key] != self.dev.states[key]:
                newStates.append({'key':key,'value':value})
                if key == 'onOffState':
                    self.logger.info('"{0}" {1}'.format(self.name, ['off','on'][value]))
                elif key == 'state':
                    self.dev.updateStateImageOnServer(k_stateImages[self.stateImg])

        if len(newStates) > 0:
            if self.plugin.debug: # don't fill up plugin log unless actively debugging
                self.logger.debug('updating states on device "{0}":'.format(self.name))
                for item in newStates:
                    self.logger.debug('{:>16}: {}'.format(item['key'],item['value']))
            self.dev.updateStatesOnServer(newStates)
        self.states = self.dev.states

    #-------------------------------------------------------------------------------
    def devChanged(self, oldDev, newDev):
        if newDev.id in self.deviceStateDict:
            stateKey = self.deviceStateDict[newDev.id]
            if oldDev.states[stateKey] != newDev.states[stateKey]:
                self.tock(newDev.states[stateKey])

    #-------------------------------------------------------------------------------
    def varChanged(self, oldVar, newVar):
        if newVar.id in self.variableList:
            if oldVar.value != newVar.value:
                self.tock(newVar.value)

    #-------------------------------------------------------------------------------
    def getChangeBool(self, value):
        if self.anyChange:
            result = True
        else:
            result = False
            if zint(value):
                result = True
            elif isinstance(value, basestring):
                result = value.lower() in k_commonTrueStates
            if self.reverse:
                result = not result
        return result

    #-------------------------------------------------------------------------------
    def delta(self, cycles, units):
        multiplier = 1
        if units == 'minutes':
            multiplier = 60
        elif units == 'hours':
            multiplier = 60*60
        elif units == 'days':
            multiplier = 60*60*24
        return int(cycles)*multiplier

    #-------------------------------------------------------------------------------
    def countdown(self, value):
        hours, remainder = divmod(zint(value), 3600)
        minutes, seconds = divmod(remainder, 60)
        return '{}:{:0>2d}:{:0>2d}'.format(hours, minutes, seconds)

    #-------------------------------------------------------------------------------
    # abstract methods
    #-------------------------------------------------------------------------------
    def tick(self):
        raise NotImplementedError

    #-------------------------------------------------------------------------------
    def tock(self, newVal):
        raise NotImplementedError

    #-------------------------------------------------------------------------------
    def start(self):
        raise NotImplementedError

    #-------------------------------------------------------------------------------
    def stop(self):
        raise NotImplementedError

    #-------------------------------------------------------------------------------
    def update(self):
        raise NotImplementedError

################################################################################
class ActivityTimer(BaseTimer):

    #-------------------------------------------------------------------------------
    def __init__(self, instance, plugin):
        super(ActivityTimer, self).__init__(instance, plugin)

        self.threshold  = int(instance.pluginProps.get('countThreshold',1))
        self.extend     = instance.pluginProps.get('extend',True)
        self.anyChange  = instance.pluginProps.get('anyChange',False)
        self.resetDelta = self.delta(instance.pluginProps.get('resetCycles',1), instance.pluginProps.get('resetUnits','minutes'))
        self.offDelta   = self.delta(instance.pluginProps.get('offCycles', 10), instance.pluginProps.get('offUnits',  'minutes'))

    #-------------------------------------------------------------------------------
    def tick(self):
        reset = expired = False
        if self.states['count'] and (self.plugin.tickTime >= self.states['resetTime']):
            self.states['count'] = 0
            self.states['reset'] = True
        if self.states['onOffState'] and (self.plugin.tickTime >= self.states['offTime']):
            self.states['onOffState'] = False
            self.states['expired'] = True
        self.update()

    #-------------------------------------------------------------------------------
    def tock(self, newVal):
        if self.getChangeBool(newVal):
            detected = False
            self.states['count'] += 1
            self.states['resetTime'] = self.plugin.tickTime + self.resetDelta
            if self.states['count'] >= self.threshold:
                self.states['onOffState'] = True
                self.states['offTime'] = self.plugin.tickTime + self.offDelta
            elif self.states['onOffState'] and self.extend:
                self.states['offTime'] = self.plugin.tickTime + self.offDelta
            self.update()

    #-------------------------------------------------------------------------------
    def start(self):
        self.states['onOffState'] = True
        self.states['offTime'] = self.plugin.tickTime + self.offDelta
        self.update()

    #-------------------------------------------------------------------------------
    def stop(self):
        if self.states['count']:
            self.states['count'] = 0
            self.states['resetTime'] = self.plugin.tickTime
        if self.states['onOffState']:
            self.states['onOffState'] = False
            self.states['offTime'] = self.plugin.tickTime
        self.update()

    #-------------------------------------------------------------------------------
    def update(self):
        if self.plugin.showTimer or (self.states != self.dev.states):
            if self.states['onOffState']:
                if (self.states['count'] >= self.threshold) or (self.states['count'] and self.extend):
                    self.states['state'] = 'active'
                    self.stateImg = 'TimerOn'
                else:
                    self.states['state'] = 'persist'
                    self.stateImg = 'SensorOn'
            else:
                if self.states['count']:
                    self.states['state'] = 'accrue'
                    self.stateImg = 'TimerOff'
                else:
                    self.states['state'] = 'idle'
                    self.stateImg = 'SensorOff'

            self.states['resetString']   = datetime.fromtimestamp(self.states['resetTime']).strftime('%Y-%m-%d %T')
            self.states['offString']     = datetime.fromtimestamp(self.states['offTime']  ).strftime('%Y-%m-%d %T')
            self.states['counting']      = bool(self.states['count'])
            if self.states['onOffState']:  self.states['expired'] = False
            if self.states['counting']:    self.states['reset']   = False

            if self.plugin.showTimer:
                if self.states['state'] in ['active','persist']:
                    self.states['displayState'] = self.countdown(self.states['offTime']   - self.plugin.tickTime)
                elif self.states['state'] == 'accrue':
                    self.states['displayState'] = self.countdown(self.states['resetTime'] - self.plugin.tickTime)
            else:
                self.states['displayState'] = self.states['state']

            self.saveStates()

################################################################################
class PersistenceTimer(BaseTimer):

    #-------------------------------------------------------------------------------
    def __init__(self, instance, plugin):
        super(PersistenceTimer, self).__init__(instance, plugin)

        self.anyChange = False
        self.onDelta  = self.delta(instance.pluginProps.get('onCycles',1), instance.pluginProps.get('onUnits','minutes'))
        self.offDelta = self.delta(instance.pluginProps.get('offCycles',1), instance.pluginProps.get('offUnits','minutes'))

        # initial state
        self.state['pending'] = False
        if instance.pluginProps['trackEntity'] == 'dev':
            devId, state = self.deviceStateDict.items()[0]
            self.state['onOffState'] = self.getChangeBool(indigo.devices[devId].states[state])
        else:
            self.stste['onOffState'] = self.getChangeBool(indigo.variables[self.variableList[0]].value)
        self.update()

    #-------------------------------------------------------------------------------
    def tick(self):
        if self.states['pending']:
            if self.states['onOffState'] and self.plugin.tickTime >= self.states['offTime']:
                self.states['onOffState'] = False
                self.states['pending'] = False
            elif not self.states['onOffState'] and self.plugin.tickTime >= self.states['onTime']:
                self.states['onOffState'] = True
                self.states['pending'] = False
            self.update()

    #-------------------------------------------------------------------------------
    def tock(self, newVal):
        if self.getChangeBool(newVal) == self.states['onOffState']:
            self.states['pending'] = False
        else:
            if self.states['onOffState']:
                self.states['offTime'] = self.plugin.tickTime + self.offDelta
            else:
                self.states['onTime'] = self.plugin.tickTime + self.onDelta
            self.states['pending'] = True
        self.update()

    #-------------------------------------------------------------------------------
    def start(self):
        pass

    #-------------------------------------------------------------------------------
    def stop(self):
        pass

    #-------------------------------------------------------------------------------
    def update(self):
        if self.plugin.showTimer or (self.states != self.dev.states):

            if self.states['onOffState']:
                if self.states['pending']:
                    self.states['state'] = 'pending'
                    self.stateImg = 'TimerOn'
                else:
                    self.states['state'] = 'on'
                    self.stateImg = 'SensorOn'
            else:
                if self.states['pending']:
                    self.states['state'] = 'pending'
                    self.stateImg = 'TimerOff'
                else:
                    self.states['state'] = 'off'
                    self.stateImg = 'SensorOff'

            self.states['onString']   = datetime.fromtimestamp(self.states['onTime']).strftime('%Y-%m-%d %T')
            self.states['offString']  = datetime.fromtimestamp(self.states['offTime']).strftime('%Y-%m-%d %T')

            if self.plugin.showTimer and self.states['pending']:
                if self.states['onOffState']:
                    self.states['displayState'] = self.countdown(self.states['offTime'] - self.plugin.tickTime)
                else:
                    self.states['displayState'] = self.countdown(self.states['onTime'] - self.plugin.tickTime)
            else:
                self.states['displayState'] = self.states['state']

            self.saveStates()


################################################################################
# Utilities
################################################################################

def zint(value):
    try:
        return int(value)
    except:
        return 0
