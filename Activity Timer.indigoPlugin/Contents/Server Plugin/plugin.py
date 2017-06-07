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
    'idle':     indigo.kStateImageSel.SensorOff,
    'accrue':   indigo.kStateImageSel.TimerOff,
    'active':   indigo.kStateImageSel.SensorOn,
    'persist':  indigo.kStateImageSel.TimerOn,
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
            self.deviceDict[dev.id] = self.ActivityTimer(dev, self)

    #-------------------------------------------------------------------------------
    def deviceStopComm(self, dev):
        self.logger.debug("deviceStopComm: "+dev.name)
        if dev.id in self.deviceDict:
            del self.deviceDict[dev.id]

    #-------------------------------------------------------------------------------
    def validateDeviceConfigUi(self, valuesDict, typeId, devId, runtime=False):
        self.logger.debug("validateDeviceConfigUi: " + typeId)
        errorsDict = indigo.Dict()

        for devKey, stateKey in k_deviceKeys:
            if zint(valuesDict.get(devKey,'')) and not valuesDict.get(stateKey,''):
                errorsDict[stateKey] = "Required"
        for key in ['countThreshold','resetCycles','offCycles']:
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
            # update local copy (will be removed/overwritten if communication is stopped/re-started)
            if newDev.id in self.deviceDict:
                self.deviceDict[newDev.id] = self.ActivityTimer(newDev, self)
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
    class ActivityTimer(object):

        #-------------------------------------------------------------------------------
        def __init__(self, instance, plugin):
            self.dev        = instance
            self.id         = instance.id
            self.name       = instance.name
            self.states     = instance.states

            self.plugin     = plugin
            self.logger     = plugin.logger

            self.threshold  = int(instance.pluginProps.get('countThreshold',1))
            self.extend     = instance.pluginProps.get('extend',True)
            self.anyChange  = instance.pluginProps.get('anyChange',False)
            self.reverse    = instance.pluginProps.get('reverseBoolean',False)
            self.resetDelta = self.delta(instance.pluginProps.get('resetCycles',1), instance.pluginProps.get('resetUnits','minutes'))
            self.offDelta   = self.delta(instance.pluginProps.get('offCycles', 10), instance.pluginProps.get('offUnits',  'minutes'))

            self.deviceStateDict = dict()
            for deviceKey, stateKey in k_deviceKeys:
                if zint(instance.pluginProps.get(deviceKey,'')):
                    self.deviceStateDict[int(instance.pluginProps[deviceKey])] = instance.pluginProps[stateKey]

            self.variableList = list()
            for variableKey in k_variableKeys:
                if zint(instance.pluginProps.get(variableKey,'')):
                    self.variableList.append(int(instance.pluginProps[variableKey]))

        #-------------------------------------------------------------------------------
        def tick(self):
            reset = expired = False
            if self.states['count'] and (self.plugin.tickTime >= self.states['resetTime']):
                self.states['count'] = 0
                self.states['reset'] = True
            if self.states['onOffState'] and (self.plugin.tickTime >= self.states['offTime']):
                self.states['onOffState'] = False
                self.states['expired'] = True
            self.save()

        #-------------------------------------------------------------------------------
        def tock(self):
            detected = False
            self.states['count'] += 1
            self.states['resetTime'] = self.plugin.tickTime + self.resetDelta
            if self.states['count'] >= self.threshold:
                self.states['onOffState'] = True
                self.states['offTime'] = self.plugin.tickTime + self.offDelta
            elif self.states['onOffState'] and self.extend:
                self.states['offTime'] = self.plugin.tickTime + self.offDelta
            self.save()

        #-------------------------------------------------------------------------------
        def start(self):
            self.states['onOffState'] = True
            self.states['offTime'] = self.plugin.tickTime + self.offDelta
            self.save()

        #-------------------------------------------------------------------------------
        def stop(self):
            if self.states['count']:
                self.states['count'] = 0
                self.states['resetTime'] = self.plugin.tickTime
            if self.states['onOffState']:
                self.states['onOffState'] = False
                self.states['offTime'] = self.plugin.tickTime
            self.save()

        #-------------------------------------------------------------------------------
        def save(self):
            if self.plugin.showTimer or (self.states != self.dev.states):
                if self.states['onOffState']:
                    if (self.states['count'] >= self.threshold) or (self.states['count'] and self.extend):
                        self.states['state'] = 'active'
                    else:
                        self.states['state'] = 'persist'
                else:
                    if self.states['count']:
                        self.states['state'] = 'accrue'
                    else:
                        self.states['state'] = 'idle'

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

                newStates = list()
                for key, value in self.states.iteritems():
                    if self.states[key] != self.dev.states[key]:
                        newStates.append({'key':key,'value':value})
                        if key == 'onOffState':
                            self.logger.info('"{0}" {1}'.format(self.name, ['off','on'][value]))
                        elif key == 'state':
                            self.dev.updateStateImageOnServer(k_stateImages[value])

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
                    if self.testChange(newDev.states[stateKey]):
                        self.tock()

        #-------------------------------------------------------------------------------
        def varChanged(self, oldVar, newVar):
            if newVar.id in self.variableList:
                if oldVar.value != newVar.value:
                    if self.testChange(newVar.value):
                        self.tock()

        #-------------------------------------------------------------------------------
        def testChange(self, value):
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

################################################################################
# Utilities
################################################################################

def zint(value):
    try:
        return int(value)
    except:
        return 0
