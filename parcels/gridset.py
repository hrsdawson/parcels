import numpy as np
import functools
from parcels.tools.loggers import logger

__all__ = ['GridSet']


class GridSet(object):
    """GridSet class that holds the Grids on which the Fields are defined

    """

    def __init__(self):
        self.grids = []

    def add_grid(self, field):
        grid = field.grid
        existing_grid = False
        for g in self.grids:
            sameGrid = True
            if grid.time_origin != g.time_origin:
                continue
            for attr in ['lon', 'lat', 'depth', 'time']:
                gattr = getattr(g, attr)
                gridattr = getattr(grid, attr)
                if gattr.shape != gridattr.shape or not np.allclose(gattr, gridattr):
                    sameGrid = False
                    break
            if not sameGrid:
                continue
            existing_grid = True
            tmp_grid = field.grid
            field.grid = g
            if tmp_grid.master_chunksize != g.master_chunksize:
                res = False
                if (isinstance(tmp_grid.master_chunksize, tuple) and isinstance(g.master_chunksize, tuple)) or \
                        (isinstance(tmp_grid.master_chunksize, dict) and isinstance(g.master_chunksize, dict)):
                    res |= functools.reduce(lambda i, j: i and j,
                                            map(lambda m, k: m == k, tmp_grid.master_chunksize, g.master_chunksize), True)
                else:
                    res |= (tmp_grid.master_chunksize == g.master_chunksize)
                if tmp_grid.master_chunksize != g.master_chunksize:
                    if res:
                        logger.warning("Trying to initialize a shared grid with different chunking sizes - action prohibited. Replacing requested field_chunksize with grid's master chunksize.")
                    else:
                        raise ValueError(
                            "Conflict between grids of the same gridset: major grid chunksize and requested sibling-grid chunksize as well as their chunk-dimension names are not equal - Please apply the same chunksize to all fields in a shared grid!")
            break

        if not existing_grid:
            self.grids.append(grid)
        field.igrid = self.grids.index(field.grid)

    def dimrange(self, dim):
        """Returns maximum value of a dimension (lon, lat, depth or time)
           on 'left' side and minimum value on 'right' side for all grids
           in a gridset. Useful for finding e.g. longitude range that
           overlaps on all grids in a gridset"""

        maxleft, minright = (-np.inf, np.inf)
        for g in self.grids:
            if len(getattr(g, dim)) == 1:
                continue  # not including grids where only one entry
            else:
                if dim == 'depth':
                    maxleft = max(maxleft, np.min(getattr(g, dim)))
                    minright = min(minright, np.max(getattr(g, dim)))
                else:
                    maxleft = max(maxleft, getattr(g, dim)[0])
                    minright = min(minright, getattr(g, dim)[-1])
        maxleft = 0 if maxleft == -np.inf else maxleft  # if all len(dim) == 1
        minright = 0 if minright == np.inf else minright  # if all len(dim) == 1
        return maxleft, minright

    @property
    def size(self):
        return len(self.grids)
