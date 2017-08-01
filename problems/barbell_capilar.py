import dolfin as df
import os
from . import *
from common.io import mpi_is_root, load_mesh
from common.bcs import Fixed, Charged
import numpy as np
__author__ = "Asger Bolet"

class Left(df.SubDomain):
    def inside(self, x, on_boundary):
        return bool(df.near(x[0],0.0) and on_boundary)

class Right(df.SubDomain):
    def __init__(self, Lx):
        self.Lx = Lx
        df.SubDomain.__init__(self)

    def inside(self, x, on_boundary):
        return bool(df.near(x[0], self.Lx) and on_boundary )


class PeriodicBoundary(df.SubDomain):
    # Left boundary is target domain
    def __init__(self, Lx):
        self.Lx = Lx
        df.SubDomain.__init__(self)

    def inside(self, x, on_boundary):
        return bool(df.near(x[0], 0.) and on_boundary)

    def map(self, x, y):
        y[0] = x[0] - self.Lx
        y[1] = x[1]


class Outer_Narrowing(df.SubDomain):
    def __init__(self, Lx, R):
        self.Lx = Lx
        self.R = R
        df.SubDomain.__init__(self)

    def inside(self, x, on_boundary):
        return bool( ((x[0] < (self.R + 1.) and x[0] >  df.DOLFIN_EPS ) or (x[0] > (self.Lx- self.R - 1.) and x[0] < self.Lx-df.DOLFIN_EPS )) and  on_boundary)


class Inner_Narrowing(df.SubDomain):
    def __init__(self, Lx, R):
        self.Lx = Lx
        self.R = R
        df.SubDomain.__init__(self)

    def inside(self, x, on_boundary):
        return bool((x[0] > (self.R + 1.) and x[0] < (self.Lx- self.R - 1.)) and  on_boundary)


def problem():
    info_cyan("Electrostatice intrusion in barbell capilar.")

    # Format: name, valency, diffusivity in phase 1, diffusivity in phase
    #         2, beta in phase 1, beta in phase 2
    solutes = [["c_p",  1, 1e-4, 1e-2, 4., 1.],
               ["c_m", -1, 1e-4, 1e-2, 4., 1.]]

    # Format: name : (family, degree, is_vector)
    base_elements = dict(u=["Lagrange", 2, True],
                         p=["Lagrange", 1, False],
                         phi=["Lagrange", 1, False],
                         g=["Lagrange", 1, False],
                         c=["Lagrange", 1, False],
                         V=["Lagrange", 1, False])

    factor = 1./4
    sigma_e =  -10.

    # Default parameters to be loaded unless starting from checkpoint.
    parameters = dict(
        solver="basic",
        folder="results_barbell_capilar",
        restart_folder=False,
        enable_NS=True,
        enable_PF=True,
        enable_EC=True,
        save_intv=5,
        stats_intv=5,
        checkpoint_intv=50,
        tstep=0,
        dt=factor*0.08,
        t_0=0.,
        T=400.,
        res=60,
        interface_thickness=factor*0.080,
        solutes=solutes,
        base_elements=base_elements,
        Lx=6.,
        Ly=2.,
        R=0.3,
        surface_charge=sigma_e,
        concentration_init=2.,
        velocity_top=.2,
        #
        surface_tension=8.45,
        grav_const=0.0,
        #
        pf_mobility_coeff=factor*0.000010,
        density=[10., 10.],
        viscosity=[1., 1.],
        permittivity=[1., 1.],
    )
    return parameters


#def constrained_domain(Lx, **namespace):
    #return PeriodicBoundary(Lx)


def mesh(Lx, Ly, res, **namespace):
    mesh = load_mesh("meshes/roundet_barbell_res" + str(res) + ".h5")
    # Check:
    # coords = mesh.coordinates()[:]
    # assert(np.max(coords[:, 0]) == Lx)
    # assert(np.max(coords[:, 1]) == Ly)
    return mesh


def initialize(Lx, Ly, R,
               interface_thickness, solutes, restart_folder,
               field_to_subspace,
               concentration_init,
               enable_NS, enable_PF, enable_EC,
               **namespace):
    """ Create the initial state. """
    w_init_field = dict()
    if not restart_folder:
        # Phase field
        if enable_PF:
            w_init_field["phi"] = initial_phasefield(
                Lx, R, interface_thickness,
                field_to_subspace["phi"])
        if enable_EC:
            for solute in solutes:
                c_init = initial_phasefield(
                    Lx, R, interface_thickness,
                    field_to_subspace["phi"])
                # Only have ions in phase 2 (phi=-1)
                c_init.vector()[:] = concentration_init*0.5*(
                    1.-c_init.vector().array())
                w_init_field[solute[0]] = c_init

    return w_init_field


def create_bcs(Lx, Ly, R,
               velocity_top, solutes,
               concentration_init, surface_charge,
               enable_NS, enable_PF, enable_EC,
               **namespace):
    """ The boundaries and boundary conditions are defined here. """
    boundaries = dict(
        outer_narrowing=[Outer_Narrowing(Lx, R)],
        inner_narrowing=[Inner_Narrowing(Lx, R)],
        right=[Right(Lx)],
        left=[Left(0)]
    )

    bcs = dict()
    for boundary_name in boundaries.keys():
        bcs[boundary_name] = dict()

    # Apply pointwise BCs e.g. to pin pressure.
    bcs_pointwise = dict()
    ground = Fixed(0.)
    noslip = Fixed((0., 0.))
    phi_inlet = Fixed(-1.0) 
    phi_outlet = Fixed(1.0) 

    if enable_NS:
        bcs["inner_narrowing"]["u"] = noslip
        bcs["outer_narrowing"]["u"] = noslip
        bcs_pointwise["p"] = (0., "x[0] < DOLFIN_EPS && x[1] > {Ly}-DOLFIN_EPS".format(Ly=Ly))

    if enable_EC:
        for solute in solutes:
            bcs["left"][solute[0]] = Fixed(concentration_init)
        bcs["left"]["V"] = ground
        bcs["outer_narrowing"]["V"] = Charged(0.0)
        bcs["inner_narrowing"]["V"] = Charged(surface_charge)
    
    if enable_PF:  
        bcs["left"]["phi"] = phi_inlet
        bcs["right"]["phi"] = phi_outlet
    return boundaries, bcs, bcs_pointwise


def initial_phasefield(Lx, R, eps, function_space):
    #expr_str = "2.*((-tanh((x[0]-(1+2*R))/(sqrt(2)*eps))+tanh((x[0]-(Lx-2*R-1))/(sqrt(2)*eps))) +0.5) "
    expr_str = "+tanh((x[0]-(1+2*R))/(sqrt(2)*eps))"
    phi_init_expr = df.Expression(expr_str, Lx=Lx, R=R, eps=eps, degree=2)
    phi_init = df.interpolate(phi_init_expr, function_space.collapse())
    return phi_init


def pf_mobility(phi, gamma):
    """ Phase field mobility function. """
    # return gamma * (phi**2-1.)**2
    # func = 1.-phi**2
    # return 0.75 * gamma * 0.5 * (1. + df.sign(func)) * func
    return gamma


def tstep_hook(t, tstep, stats_intv, statsfile, field_to_subspace,
               field_to_subproblem, subproblems, w_, **namespace):
    info_blue("Timestep = {}".format(tstep))

    if False and stats_intv and tstep % stats_intv == 0:
        # GL: Seems like a rather awkward way of doing this,
        # but any other way seems to fuck up the simulation.
        # Anyhow, a better idea could be to move some of this to a post-processing stage.
        # GL: Move into common/utilities at a certain point.
        subproblem_name, subproblem_i = field_to_subproblem["phi"]
        Q = w_[subproblem_name].split(deepcopy=True)[subproblem_i]
        bubble = df.interpolate(Q, field_to_subspace["phi"].collapse())
        bubble = 0.5*(1.-df.sign(bubble))
        mass = df.assemble(bubble*df.dx)
        massy = df.assemble(
            bubble*df.Expression("x[1]", degree=1)*df.dx)
        if mpi_is_root():
            with file(statsfile, "a") as outfile:
                outfile.write("{} {} {} \n".format(t, mass, massy))


def start_hook(newfolder, **namespace):
    statsfile = os.path.join(newfolder, "Statistics/stats.dat")
    return dict(statsfile=statsfile)
