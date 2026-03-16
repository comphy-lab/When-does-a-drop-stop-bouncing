/* Title: Bouncing Droplet!
# Author: Vatsal Sanjay
# vatsalsanjay@gmail.com
# Physics of Fluids
# Last Update April 08 2022
*/

// 1 is drop
#include "axi.h"
#include "navier-stokes/centered.h"
#define FILTERED 1
#include "two-phase.h"
#include "navier-stokes/conserving.h"
#include "tension.h"
#include "reduced.h"
#include "params.h"

// Error tolerances
#define fErr (1e-3)                                 // error tolerance in VOF
#define KErr (1e-6)                                 // error tolerance in KAPPA
#define VelErr (1e-2)                            // error tolerances in velocity
#define DissErr (1e-2)                            // error tolerances in dissipation

// air-water
#define Rho21 (1e-3)
// Calculations!
#define Xdist (1.02)
#define R2Drop(x,y) (sq(x - Xdist) + sq(y))

// boundary conditions
u.t[left] = dirichlet(0.);
// when viscosty ratio Ohd/Ohs is too high, consider using free slip for gas and no-slip for drop
// u.t[left] = dirichlet(0.)*f[] + (1-f[])*neumann(0.0);

f[left] = dirichlet(0.0);
u.n[right] = neumann(0.);
p[right] = dirichlet(0.0);
u.n[top] = neumann(0.);
p[top] = dirichlet(0.0);

int MAXlevel;
double tmax, We, Ohd, Ohs, Bo, Ldomain;
double tsnap = 0.01;
#define MINlevel 2                                            // maximum level

int main(int argc, char const *argv[]) {
  if (!params_init_from_argv(argc, argv))
    return 1;

  MAXlevel = param_int_min("MAXlevel", 10, MINlevel);
  tmax = param_double("tmax", 25.);
  We = param_double("We", 1.0);
  Ohd = param_double("Ohd", 0.1);
  Ohs = param_double("Ohs", 1e-5);
  Bo = param_double("Bo", 0.1);
  Ldomain = param_double("Ldomain", 4.0);

  fprintf(ferr,
          "params %s | Level %d tmax %g tsnap %g We %g Ohd %3.2e Ohs %3.2e Bo %g Lo %g\n",
          params_source_file(), MAXlevel, tmax, tsnap, We, Ohd, Ohs, Bo, Ldomain);

  L0=Ldomain;
  X0=0.; Y0=0.;
  init_grid (1 << (4));

  char comm[80];
  sprintf (comm, "mkdir -p intermediate");
  system(comm);

  /* For We > 1, it is useful to redefine the scales by choosing the impact velocity.
  Note that this non-dimensionalization is different from the one mentioned in the paper, which mentions Oh and Bo as the
  coefficients of viscous and gravitational terms respectively instead of Oh/sqrt(We) and Bo/We, respectively.
  Of course, these scales are inter-changeable and only differ by a factor of
  \sqrt{We}. Also, we run these cases by independently varying We, Oh and Bo. So, helpful to use them as control parameters.
  */

  rho1 = 1.0; mu1 = Ohd/sqrt(We);
  rho2 = Rho21; mu2 = Ohs/sqrt(We);
  f.sigma = 1.0/We;
  G.x = -Bo/We; // Gravity
  run();
}

event init(t = 0){
  if(!restore (file = "restart") && !restore (file = "dump")){
    refine((R2Drop(x,y) < 1.05) && (level < MAXlevel));
    fraction (f, 1. - R2Drop(x,y));
    foreach () {
      u.x[] = -1.0*f[];
      u.y[] = 0.0;
    }
    boundary((scalar *){f, u.x, u.y});
  }
}

scalar KAPPA[], D2c[];

event adapt(i++){
  curvature(f, KAPPA);
  foreach(){
    double D11 = (u.y[0,1] - u.y[0,-1])/(2*Delta);
    double D22 = (u.y[]/max(y,1e-20));
    double D33 = (u.x[1,0] - u.x[-1,0])/(2*Delta);
    double D13 = 0.5*( (u.y[1,0] - u.y[-1,0] + u.x[0,1] - u.x[0,-1])/(2*Delta) );
    double D2 = (sq(D11)+sq(D22)+sq(D33)+2.0*sq(D13));
    D2c[] = f[]*D2;
  }
  adapt_wavelet ((scalar *){f, KAPPA, u.x, u.y, D2c},
     (double[]){fErr, KErr, VelErr, VelErr, DissErr},
     MAXlevel, MINlevel);
}

// Outputs
// static
event writingFiles (t = 0; t += tsnap; t <= tmax) {
  // p.nodump = false; // uncomment this to dump pressure.
  dump (file = "restart");
  char nameOut[80];
  sprintf (nameOut, "intermediate/snapshot-%5.4f", t);
  dump (file = nameOut);
}

event stopAtTmax (t = tmax) {
  dump (file = "restart");
  return 1;
}

event logWriting (i+=10) {
  double ke = 0.;
  foreach (reduction(+:ke)){
    ke += 2*pi*y*(0.5*rho(f[])*(sq(u.x[]) + sq(u.y[])))*sq(Delta);
  }

  // double pdatum = 0, wt = 0;
  // foreach_boundary(top, reduction(+:pdatum), reduction(+:wt)){
  //   pdatum += 2*pi*y*p[]*(Delta);
  //   wt += 2*pi*y*(Delta);
  // }
  // if (wt >0){
  //   pdatum /= wt;
  // }

  // double pforce = 0.;
  // foreach_boundary(left, reduction(+:pforce)){
  //   pForce += 2*pi*y*(p[]-pdatum)*(Delta);
  // }

  static FILE * fp;
  if (i == 0) {
    fprintf (ferr, "i dt t ke p\n");
    fp = fopen ("log", "w");
    fprintf(fp, "Level %d tmax %g. We %g, Ohd %3.2e, Ohs %3.2e, Bo %g\n", MAXlevel, tmax, We, Ohd, Ohs, Bo);
    // fprintf (fp, "i dt t ke p\n");
    // fprintf (fp, "%d %g %g %g %g\n", i, dt, t, ke, pforce);
    fprintf (fp, "i dt t ke\n");
    fprintf (fp, "%d %g %g %g\n", i, dt, t, ke);
    fclose(fp);
  } else {
    fp = fopen ("log", "a");
    // fprintf (fp, "%d %g %g %g %g\n", i, dt, t, ke, pforce);
    fprintf (fp, "%d %g %g %g\n", i, dt, t, ke);
    fclose(fp);
  }
  // fprintf (ferr, "%d %g %g %g %g\n", i, dt, t, ke, pforce);
  fprintf (ferr, "%d %g %g %g\n", i, dt, t, ke);

  if (ke < 1e-6){
    fprintf(ferr,"Done!");
    return 1;
  }
}
