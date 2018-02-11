from __future__ import print_function
from fenics import *
import numpy as np
import os, sys
import scipy.io

from collections import OrderedDict

# Set log level
set_log_level(WARNING)

# Prepare a mesh
#mesh = UnitIntervalMesh(100)
mesh = UnitSquareMesh(10,10)

# Choose a time step size
k = Constant(1e-2)

# MPC horizon length
N = 10

# boundary heat conductivity parameters
alpha = Constant(1.0)
beta = Constant(1.0)
gamma = Constant(1.0e3)

# Compile sub domains for boundaries
tol = 1e-14
left = CompiledSubDomain("near(x[0], 0.)")
top = CompiledSubDomain("near(x[1], 1.)")
bot = CompiledSubDomain("near(x[1], 0.)")



class controldomain(SubDomain):
    def inside(self, x, on_boundary):
        return near(x[0], 1.) and (x[1] >= 0.4 - tol) and (x[1] <= 0.6 + tol)

class restdomain(SubDomain):
    def inside(self, x, on_boundary):
        return near(x[0], 1.) and ((x[1] < 0.4) or (x[1] > 0.6))

control = controldomain()
right = restdomain()

# Label boundaries, required for the objective
boundary_parts = MeshFunction("size_t", mesh, mesh.topology().dim() - 1)
left.mark(boundary_parts, 0)    # boundary part for outside temperature
top.mark(boundary_parts, 0)    # boundary part for outside temperature
bot.mark(boundary_parts, 0)    # boundary part for outside temperature
right.mark(boundary_parts, 0)   # boundary part for outside temperature
control.mark(boundary_parts, 1)   # boundary part where control is applied
ds = Measure("ds", subdomain_data=boundary_parts)

#class VelocityFieldExpression(Expression):
#    def eval(self, value, x):
#        value[0] = -1.0

#    def value_shape(self):
#        return (1,)

def output_matrices():
    # Define function space
    parameters.linear_algebra_backend = "Eigen"

    U = FunctionSpace(mesh, "Lagrange", 1)
#    W = VectorFunctionSpace(mesh, 'P', 1, dim=1)

    # Define test and trial functions
    v = TestFunction(U)
    y = TrialFunction(U)
    y0 = TrialFunction(U)

    u = Constant(1.0)
    y_out = Constant(1.0)

#    w = Function(W)
#    e = VelocityFieldExpression(domain=mesh, degree=1)
#    w = interpolate(e, W)

    # Define variational formulation
    a = (y / k * v + alpha * inner(grad(y), grad(v))) * dx + alpha * gamma/beta * y * v * ds
#    f_w = dot(w, grad(y)) * v * dx
    f_y = y0 / k * v * dx

    f_y_out = alpha * gamma/beta * y_out * v * ds(0)

    f_u = alpha * gamma / beta * u * v * ds(1)

    A = assemble(a)

#    B_w = assemble(f_w)
    B_y = assemble(f_y)

    b_u = assemble(f_u)
    b_y_out = assemble(f_y_out)

    # output matrices for use in matlab optimization

    A_re = as_backend_type(A).sparray()
    scipy.io.mmwrite("A.mtx", A_re, symmetry="general")

#    B_w_re = as_backend_type(B_w).sparray()
#    scipy.io.mmwrite("B_w.mtx", B_w_re, symmetry="general")

    B_y_re = as_backend_type(B_y).sparray()
    scipy.io.mmwrite("B_y.mtx", B_y_re, symmetry="general")


#save coordinates of degree of freedoms (vertices with linear elements)
    gdim = mesh.geometry().dim()
    dofs = U.tabulate_dof_coordinates().reshape((-1, gdim))
    dof_file_x = open("dof_x.txt", "w")
    dof_file_y = open("dof_y.txt", "w")
    for val in dofs:
        dof_file_x.write(str(val[0]) + "\n")
        dof_file_y.write(str(val[1]) + "\n")
    dof_file_x.close
    dof_file_y.close



    b_u_re = b_u.array()
    b_u_file = open("b_u.txt", "w")
    b_u_file.write(str(len(b_u_re)) + "\n")
    for val in b_u_re:
        b_u_file.write(str(val) + "\n")
    b_u_file.close()

    b_y_out_re = b_y_out.array()
    b_y_out_file = open("b_y_out.txt", "w")
    b_y_out_file.write(str(len(b_y_out_re)) + "\n")
    for val in b_y_out_re:
        b_y_out_file.write(str(val) + "\n")
    b_y_out_file.close()

    param_file = open("parameters.txt", "w")
    param_file.write(str(float((alpha))) + " alpha \n")
    param_file.write(str(float((beta))) + " beta \n")
    param_file.write(str(float((gamma))) + " gamma \n")
    param_file.close()

    return b_u, b_y_out



def solve_forward(us, y_outs, record=False):

    """ The forward problem """
    ofile = File("results/y.pvd")

    # Define function spaces
    U = FunctionSpace(mesh, "Lagrange", 1)
    W = VectorFunctionSpace(mesh, 'P', 1, dim=1)

    # Set up initial values
    y0 = Function(U, name="y0")
    y0 = interpolate(Expression("0.5",degree=1), U)

    # Define test and trial functions
    v = TestFunction(U)
    y = TrialFunction(U)
    u = Constant(1.0)
    y_out = Constant(1.0)
    #vv = Function(U)
    #vv = Expression("0.0",domain=mesh, degree=1)
    #b = Expression(("-(x[1]-0.5)","(x[0]-0.5)"), domain=mesh, degree=1)
    #vv= Function(U)
    #vv = interpolate(b, U)
    #vv = Constant(1.0)
    w = Function(W)
    e = VelocityFieldExpression(domain=mesh, degree=1)
    w = interpolate(e, W)

    # Define variational formulation
    a = (y/k * v + alpha * inner(grad(y), grad(v))) * dx + alpha * gamma/beta * y * v * ds
    f_y = (y0 / k * v + dot(w, grad(y0)) * v ) * dx

    f_u = alpha * gamma/beta * u * v * ds(1)

    f_y_out = alpha * gamma/beta * y_out * v * ds(0)

    # Prepare solution
    y = Function(U, name="y")

    i = 0

    ys = OrderedDict()
    y_omegas = OrderedDict()
    y_omegas[i] = Function(U, name="y_omega[0]")

    L = min(len(us), len(y_outs))

    while i < L:
        plot(y0)
        u.assign(us[i])
        y_out.assign(y_outs[i])

        solve(a == f_u + f_y + f_y_out, y)
        y0.assign(y)

        i += 1

    scipy.io.savemat('y.mat', {'y': y.vector().array()})


    return y, ys, y_omegas


if __name__ == "__main__":

   output_matrices()

    # L = 200
    #
    # us = np.array([0.5 for i in range(0,L)])
    # y_outs = np.array([0.5 + 1.0/3.0 * sin(i/10.0) for i in range(0,L)])
    #
    # solve_forward(us, y_outs)