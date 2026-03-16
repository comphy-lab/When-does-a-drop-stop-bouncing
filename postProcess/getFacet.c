/**
# Interface Facet Extractor

Small Basilisk helper that restores a snapshot and writes the reconstructed VOF
interface facets to `stderr`. Downstream Python tools read this output to draw
the liquid outline on rendered frames.
*/
#include "navier-stokes/centered.h"
#include "fractions.h"

scalar f[];
char filename[80];

/**
### main()

#### Parameters

- `arguments[1]`: Path to the Basilisk dump or snapshot file
*/
int main(int a, char const *arguments[])
{
  sprintf (filename, "%s", arguments[1]);
  restore (file = filename);
  f[left] = dirichlet(0.);
  f.prolongation = fraction_refine;
  boundary(all);
  FILE * fp = ferr;
  output_facets(f,fp);
  fflush (fp);
  fclose (fp);
}
