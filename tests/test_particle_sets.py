from parcels import (FieldSet, ParticleSet, Field, ScipyParticle, JITParticle,
                     Variable, ErrorCode)
import numpy as np
import pytest
from netCDF4 import Dataset

ptype = {'scipy': ScipyParticle, 'jit': JITParticle}


@pytest.fixture
def fieldset(xdim=40, ydim=100):
    U = np.zeros((ydim, xdim), dtype=np.float32)
    V = np.zeros((ydim, xdim), dtype=np.float32)
    lon = np.linspace(0, 1, xdim, dtype=np.float32)
    lat = np.linspace(-60, 60, ydim, dtype=np.float32)
    depth = np.zeros(1, dtype=np.float32)
    time = np.zeros(1, dtype=np.float64)
    data = {'U': np.array(U, dtype=np.float32), 'V': np.array(V, dtype=np.float32)}
    dimensions = {'lat': lat, 'lon': lon, 'depth': depth, 'time': time}
    return FieldSet.from_data(data, dimensions)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_create_lon_lat(fieldset, mode, npart=100):
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    pset = ParticleSet(fieldset, lon=lon, lat=lat, pclass=ptype[mode])
    assert np.allclose([p.lon for p in pset], lon, rtol=1e-12)
    assert np.allclose([p.lat for p in pset], lat, rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_create_line(fieldset, mode, npart=100):
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    pset = ParticleSet.from_line(fieldset, size=npart, start=(0, 1), finish=(1, 0), pclass=ptype[mode])
    assert np.allclose([p.lon for p in pset], lon, rtol=1e-12)
    assert np.allclose([p.lat for p in pset], lat, rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy'])
def test_pset_create_field(fieldset, mode, npart=100):
    np.random.seed(123456)
    shape = (fieldset.U.lon.size, fieldset.U.lat.size)
    K = Field('K', lon=fieldset.U.lon, lat=fieldset.U.lat,
              data=np.ones(shape, dtype=np.float32), transpose=True)
    pset = ParticleSet.from_field(fieldset, size=npart, pclass=ptype[mode], start_field=K)
    assert (np.array([p.lon for p in pset]) <= K.lon[-1]).all()
    assert (np.array([p.lon for p in pset]) >= K.lon[0]).all()
    assert (np.array([p.lat for p in pset]) <= K.lat[-1]).all()
    assert (np.array([p.lat for p in pset]) >= K.lat[0]).all()


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_create_with_time(fieldset, mode, npart=100):
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    time = 5.
    pset = ParticleSet(fieldset, lon=lon, lat=lat, pclass=ptype[mode], time=time)
    assert np.allclose([p.time for p in pset], time, rtol=1e-12)
    pset = ParticleSet.from_list(fieldset, lon=lon, lat=lat, pclass=ptype[mode],
                                 time=[time]*npart)
    assert np.allclose([p.time for p in pset], time, rtol=1e-12)
    pset = ParticleSet.from_line(fieldset, size=npart, start=(0, 1), finish=(1, 0),
                                 pclass=ptype[mode], time=time)
    assert np.allclose([p.time for p in pset], time, rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_repeated_release(fieldset, mode, npart=10):
    time = np.arange(0, npart, 1)  # release 1 particle every second
    pset = ParticleSet(fieldset, lon=np.zeros(npart), lat=np.zeros(npart),
                       pclass=ptype[mode], time=time)
    assert np.allclose([p.time for p in pset], time)

    def IncrLon(particle, fieldset, time, dt):
        particle.lon += 1.
    pset.execute(IncrLon, dt=1., runtime=npart)
    assert np.allclose([p.lon for p in pset], np.arange(npart, 0, -1))


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('repeatdt', range(1, 3))
@pytest.mark.parametrize('dt', [-1, 1])
@pytest.mark.parametrize('maxvar', [2, 4, 10])
def test_pset_repeated_release_delayed_adding_deleting(fieldset, mode, repeatdt, tmpdir, dt, maxvar, runtime=10):
    fieldset.maxvar = maxvar

    class MyParticle(ptype[mode]):
        sample_var = Variable('sample_var', initial=0.)
    pset = ParticleSet(fieldset, lon=[0], lat=[0], pclass=MyParticle, repeatdt=repeatdt)
    outfilepath = tmpdir.join("pfile_repeatdt")
    pfile = pset.ParticleFile(outfilepath, outputdt=abs(dt))

    def IncrLon(particle, fieldset, time, dt):
        particle.sample_var += 1.
        if particle.sample_var > fieldset.maxvar:
            particle.delete()
    for i in range(runtime):
        pset.execute(IncrLon, dt=dt, runtime=1., output_file=pfile)
    assert np.allclose([p.sample_var for p in pset], np.arange(maxvar, -1, -repeatdt))
    ncfile = Dataset(outfilepath+".nc", 'r', 'NETCDF4')
    samplevar = ncfile.variables['sample_var'][:]
    assert samplevar.shape == (runtime // repeatdt+1, min(maxvar+1, runtime)+1)
    if repeatdt == 0:
        # test whether samplevar[i, i+k] = k for k=range(maxvar)
        for k in range(maxvar):
            for i in range(runtime-k):
                assert(samplevar[i, i+k] == k)


def test_pset_repeatdt_check_dt(fieldset):
    pset = ParticleSet(fieldset, lon=[0], lat=[0], pclass=ScipyParticle, repeatdt=5)

    def IncrLon(particle, fieldset, time, dt):
        particle.lon = 1.
    pset.execute(IncrLon, dt=2, runtime=21)
    assert np.allclose([p.lon for p in pset], 1)  # if p.dt is nan, it won't be executed so p.lon will be 0


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_access(fieldset, mode, npart=100):
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    pset = ParticleSet(fieldset, lon=lon, lat=lat, pclass=ptype[mode])
    assert(pset.size == 100)
    assert np.allclose([pset[i].lon for i in range(pset.size)], lon, rtol=1e-12)
    assert np.allclose([pset[i].lat for i in range(pset.size)], lat, rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_custom_ptype(fieldset, mode, npart=100):
    class TestParticle(ptype[mode]):
        user_vars = {'p': np.float32, 'n': np.int32}

        def __init__(self, *args, **kwargs):
            super(TestParticle, self).__init__(*args, **kwargs)
            self.p = 0.33
            self.n = 2

    pset = ParticleSet(fieldset, pclass=TestParticle,
                       lon=np.linspace(0, 1, npart, dtype=np.float32),
                       lat=np.linspace(1, 0, npart, dtype=np.float32))
    assert(pset.size == 100)
    # FIXME: The float test fails with a conversion error of 1.e-8
    # assert np.allclose([p.p - 0.33 for p in pset], np.zeros(npart), rtol=1e-12)
    assert np.allclose([p.n - 2 for p in pset], np.zeros(npart), rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_add_explicit(fieldset, mode, npart=100):
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    pset = ParticleSet(fieldset, lon=[], lat=[], pclass=ptype[mode])
    for i in range(npart):
        particle = ptype[mode](lon=lon[i], lat=lat[i], fieldset=fieldset)
        pset.add(particle)
    assert(pset.size == 100)
    assert np.allclose([p.lon for p in pset], lon, rtol=1e-12)
    assert np.allclose([p.lat for p in pset], lat, rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_add_shorthand(fieldset, mode, npart=100):
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    pset = ParticleSet(fieldset, lon=[], lat=[], pclass=ptype[mode])
    for i in range(npart):
        pset += ptype[mode](lon=lon[i], lat=lat[i], fieldset=fieldset)
    assert(pset.size == 100)
    assert np.allclose([p.lon for p in pset], lon, rtol=1e-12)
    assert np.allclose([p.lat for p in pset], lat, rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_add_execute(fieldset, mode, npart=10):
    def AddLat(particle, fieldset, time, dt):
        particle.lat += 0.1

    pset = ParticleSet(fieldset, lon=[], lat=[], pclass=ptype[mode])
    for i in range(npart):
        pset += ptype[mode](lon=0.1, lat=0.1, fieldset=fieldset)
    for _ in range(3):
        pset.execute(pset.Kernel(AddLat), runtime=1., dt=1.0)
    assert np.allclose(np.array([p.lat for p in pset]), 0.4, rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_merge_inplace(fieldset, mode, npart=100):
    pset1 = ParticleSet(fieldset, pclass=ptype[mode],
                        lon=np.linspace(0, 1, npart, dtype=np.float32),
                        lat=np.linspace(1, 0, npart, dtype=np.float32))
    pset2 = ParticleSet(fieldset, pclass=ptype[mode],
                        lon=np.linspace(0, 1, npart, dtype=np.float32),
                        lat=np.linspace(0, 1, npart, dtype=np.float32))
    assert(pset1.size == 100)
    assert(pset2.size == 100)
    pset1.add(pset2)
    assert(pset1.size == 200)


@pytest.mark.xfail(reason="ParticleSet duplication has not been implemented yet")
@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_merge_duplicate(fieldset, mode, npart=100):
    pset1 = ParticleSet(fieldset, pclass=ptype[mode],
                        lon=np.linspace(0, 1, npart, dtype=np.float32),
                        lat=np.linspace(1, 0, npart, dtype=np.float32))
    pset2 = ParticleSet(fieldset, pclass=ptype[mode],
                        lon=np.linspace(0, 1, npart, dtype=np.float32),
                        lat=np.linspace(0, 1, npart, dtype=np.float32))
    pset3 = pset1 + pset2
    assert(pset1.size == 100)
    assert(pset2.size == 100)
    assert(pset3.size == 200)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_remove_index(fieldset, mode, npart=100):
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    pset = ParticleSet(fieldset, lon=lon, lat=lat, pclass=ptype[mode])
    for ilon, ilat in zip(lon[::-1], lat[::-1]):
        p = pset.remove(-1)
        assert(p.lon == ilon)
        assert(p.lat == ilat)
    assert(pset.size == 0)


@pytest.mark.xfail(reason="Particle removal has not been implemented yet")
@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_remove_particle(fieldset, mode, npart=100):
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    pset = ParticleSet(fieldset, lon=lon, lat=lat, pclass=ptype[mode])
    for ilon, ilat in zip(lon[::-1], lat[::-1]):
        p = pset.remove(pset[-1])
        assert(p.lon == ilon)
        assert(p.lat == ilat)
    assert(pset.size == 0)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_remove_kernel(fieldset, mode, npart=100):
    def DeleteKernel(particle, fieldset, time, dt):
        if particle.lon >= .4:
            particle.delete()

    pset = ParticleSet(fieldset, pclass=ptype[mode],
                       lon=np.linspace(0, 1, npart, dtype=np.float32),
                       lat=np.linspace(1, 0, npart, dtype=np.float32))
    pset.execute(pset.Kernel(DeleteKernel), endtime=1., dt=1.0)
    assert(pset.size == 40)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_multi_execute(fieldset, mode, npart=10, n=5):
    def AddLat(particle, fieldset, time, dt):
        particle.lat += 0.1

    pset = ParticleSet(fieldset, pclass=ptype[mode],
                       lon=np.linspace(0, 1, npart, dtype=np.float32),
                       lat=np.zeros(npart, dtype=np.float32))
    k_add = pset.Kernel(AddLat)
    for _ in range(n):
        pset.execute(k_add, runtime=1., dt=1.0)
    assert np.allclose([p.lat - n*0.1 for p in pset], np.zeros(npart), rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pset_multi_execute_delete(fieldset, mode, npart=10, n=5):
    def AddLat(particle, fieldset, time, dt):
        particle.lat += 0.1

    pset = ParticleSet(fieldset, pclass=ptype[mode],
                       lon=np.linspace(0, 1, npart, dtype=np.float32),
                       lat=np.zeros(npart, dtype=np.float32))
    k_add = pset.Kernel(AddLat)
    for _ in range(n):
        pset.execute(k_add, runtime=1., dt=1.0)
        pset.remove(-1)
    assert np.allclose([p.lat - n*0.1 for p in pset], np.zeros(npart - n), rtol=1e-12)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('area_scale', [True, False])
def test_density(fieldset, mode, area_scale):
    lons, lats = np.meshgrid(np.linspace(0.05, 0.95, 10), np.linspace(-30, 30, 20))
    pset = ParticleSet(fieldset, pclass=ptype[mode], lon=lons, lat=lats)
    arr = pset.density(area_scale=area_scale)
    if area_scale:
        assert np.allclose(arr, 1 / fieldset.U.cell_areas(), rtol=1e-3)  # check that density equals 1/area
    else:
        assert(np.sum(arr) == lons.size)  # check conservation of particles
        inds = np.where(arr)
        for i in range(len(inds[0])):  # check locations (low atol because of coarse grid)
            assert np.allclose(fieldset.U.lon[inds[1][i]], pset[i].lon, atol=fieldset.U.lon[1]-fieldset.U.lon[0])
            assert np.allclose(fieldset.U.lat[inds[0][i]], pset[i].lat, atol=fieldset.U.lat[1]-fieldset.U.lat[0])


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pfile_array_remove_particles(fieldset, mode, tmpdir, npart=10):
    filepath = tmpdir.join("pfile_array_remove_particles")
    pset = ParticleSet(fieldset, pclass=ptype[mode],
                       lon=np.linspace(0, 1, npart, dtype=np.float32),
                       lat=0.5*np.ones(npart, dtype=np.float32))
    pfile = pset.ParticleFile(filepath)
    pfile.write(pset, 0)
    pset.remove(3)
    pfile.write(pset, 1)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_pfile_array_remove_all_particles(fieldset, mode, tmpdir, npart=10):

    filepath = tmpdir.join("pfile_array_remove_particles")
    pset = ParticleSet(fieldset, pclass=ptype[mode],
                       lon=np.linspace(0, 1, npart, dtype=np.float32),
                       lat=0.5*np.ones(npart, dtype=np.float32))
    pfile = pset.ParticleFile(filepath)
    pfile.write(pset, 0)
    for _ in range(npart):
        pset.remove(-1)
    pfile.write(pset, 1)
    pfile.write(pset, 2)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('npart', [1, 2, 5])
def test_variable_written_once(fieldset, mode, tmpdir, npart):
    filepath = tmpdir.join("pfile_once_written_variables")

    def Update_v(particle, fieldset, time, dt):
        particle.v_once += 1.
        particle.age += dt

    class MyParticle(ptype[mode]):
        v_once = Variable('v_once', dtype=np.float32, initial=0., to_write='once')
        age = Variable('age', dtype=np.float32, initial=0.)
    lon = np.linspace(0, 1, npart, dtype=np.float32)
    lat = np.linspace(1, 0, npart, dtype=np.float32)
    pset = ParticleSet(fieldset, pclass=MyParticle, lon=lon, lat=lat, repeatdt=0.1)
    pset.execute(pset.Kernel(Update_v), endtime=1, dt=0.1,
                 output_file=pset.ParticleFile(name=filepath, outputdt=0.1))
    assert np.allclose([p.v_once - p.age * 10 for p in pset], 0, atol=1e-5)
    ncfile = Dataset(filepath+".nc", 'r', 'NETCDF4')
    vfile = ncfile.variables['v_once'][:]
    assert (vfile.shape == (npart*11, ))
    assert [v == 0 for v in vfile]


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_variable_written_ondelete(fieldset, mode, tmpdir, npart=3):
    filepath = tmpdir.join("pfile_on_delete_written_variables")

    def move_west(particle, fieldset, time, dt):
        tmp = fieldset.U[time, particle.lon, particle.lat, particle.depth]  # to trigger out-of-bounds error
        particle.lon -= 0.1 + tmp

    def DeleteP(particle, fieldset, time, dt):
        particle.delete()

    lon = np.linspace(0.05, 0.95, npart, dtype=np.float32)
    lat = np.linspace(0.95, 0.05, npart, dtype=np.float32)

    (dt, runtime) = (0.1, 0.8)
    lon_end = lon - runtime/dt*0.1
    noutside = len(lon_end[lon_end < 0])

    pset = ParticleSet(fieldset, pclass=ptype[mode], lon=lon, lat=lat)

    outfile = pset.ParticleFile(name=filepath, write_ondelete=True)
    pset.execute(move_west, runtime=runtime, dt=dt, output_file=outfile,
                 recovery={ErrorCode.ErrorOutOfBounds: DeleteP})
    ncfile = Dataset(filepath+".nc", 'r', 'NETCDF4')
    lon = ncfile.variables['lon'][:]
    assert (lon.size == noutside)
