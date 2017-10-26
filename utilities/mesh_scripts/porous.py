""" porous script. """
from common import info
import numpy as np
import mshr
import dolfin as df
from generate_mesh import MESHES_DIR, store_mesh_HDF5


def description(**kwargs):
    info("")


def method(Lx=4., Ly=4., rad=0.2, R=0.3, N=24, n_segments=40, res=80,
           **kwargs):
    """ Porous mesh. Not really done or useful. """
    info("Generating porous mesh")

    # x = np.random.rand(N, 2)

    diam2 = 4*R**2

    pts = np.zeros((N, 2))
    for i in range(N):
        while True:
            pt = (np.random.rand(2)-0.5) * np.array([Lx-2*R, Ly-2*R])
            if i == 0:
                break
            dist = pts[:i, :] - np.outer(np.ones(i), pt)
            dist2 = dist[:, 0]**2 + dist[:, 1]**2
            if all(dist2 > diam2):
                break
        pts[i, :] = pt

    rect = mshr.Rectangle(df.Point(-Lx/2, -Ly/2), df.Point(Lx/2, Ly/2))
    domain = rect
    for i in range(N):
        domain -= mshr.Circle(df.Point(pts[i, 0], pts[i, 1]),
                              rad, segments=n_segments)

    mesh = mshr.generate_mesh(domain, res)

    df.plot(mesh)
    df.interactive()
