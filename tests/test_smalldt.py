# -*- coding: utf-8 -*-
"""
test run for debugging the small dt/tolerance bug

Created on Thu Feb 27 14:44:03 2020

@author: reint fischer
"""

# Local Parcels path for Reint
# import sys
#
# sys.path.insert(0, "\\Users\\Gebruiker\\Documents\\GitHub\\parcels\\")  # Set path to find the newest parcels code

from parcels import FieldSet, ParticleSet, JITParticle, ScipyParticle, AdvectionRK4, ErrorCode, plotTrajectoriesFile
import numpy as np
from datetime import timedelta
from os import path
import threading
import pytest


### Functions ###
@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('dt', [0.004,  -0.004, 0.01, -0.01, 0.1, -0.1])
def test_consistent_time_accumulation(mode, dt):
    def deleteparticle(particle, fieldset, time):
        """ This function deletes particles as they exit the domain and prints a message about their attributes at that moment
        """

        # print('Particle '+str(particle.id)+' has died at t = '+str(time))
        particle.delete()

    class Abortion():
        abort_object = None
        aborted = False
        def __init__(self, object):
            self.abort_object = object

        def abort(self):
            self.abort_object.aborted = True
            self.aborted = True

    ioutputdt = 0.1
    iruntime = 1.5
    outputdt = timedelta(seconds=ioutputdt)  # make this a parameter if the test result differs depending on this parameter value
    runtime = timedelta(seconds=iruntime)    # make this a parameter if the test result differs depending on this parameter value
    datafile = path.join(path.dirname(__file__), 'test_data', 'dt_field')

    fieldset = FieldSet.from_parcels(datafile, allow_time_extrapolation=True)
    lon = fieldset.U.lon
    lat = fieldset.U.lat

    lons, lats = np.meshgrid(lon[::2], lat[::2])  # meshgrid at all gridpoints in the flow data
    lons = lons.flatten()
    lats = lats.flatten()
    inittime = np.asarray([0] * len(lons))

    pset = ParticleSet(fieldset=fieldset, pclass=ScipyParticle, lon=lons, lat=lats, time=inittime)
    abort_object = Abortion(pset)
    timer = threading.Timer(iruntime/ioutputdt+1000.,abort_object.abort)

    output_file = pset.ParticleFile(name='test_data/TEST2', outputdt=outputdt)
    timer.start()
    pset.execute(AdvectionRK4,
                 runtime=runtime,
                 dt=timedelta(seconds=dt),
                 recovery={ErrorCode.ErrorOutOfBounds: deleteparticle}, output_file=output_file)
    timer.cancel()
    output_file.close()
    assert abort_object.aborted == False
    # particles = pset.particles
    # result = []
    # time_prev = 0
    # for i in range(len(particles)):
    #     result.append(particles[i].time-time_prev)
    #     time_prev = particles[i].time
    # result = np.array(result, dtype=np.float64)
    # assert np.allclose(result,dt)

    target_t = np.sign(dt) * iruntime
    particles = pset.particles
    result = []
    for i in range(len(particles)):
        result.append(particles[i].time)
    result = np.asarray(result)
    assert np.allclose(result,target_t)
