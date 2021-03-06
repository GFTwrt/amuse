/* ################################################################################## */
/* ###                                                                            ### */
/* ###                                 Gadgetmp2                                  ### */
/* ###                                                                            ### */
/* ###   Original: Gadget2 in the version used in Amuse                           ### */
/* ###   Author: Gadget2 and Amuse contributors                                   ### */
/* ###                                                                            ### */
/* ###   Modified: July 2020                                                      ### */
/* ###   Author: Thomas Schano                                                    ### */
/* ###                                                                            ### */
/* ###   Changes are intended to enable precise calculations in                   ### */
/* ###   non periodic small domain simulations in which comoving parts            ### */
/* ###   are simulated in std precision                                           ### */
/* ###                                                                            ### */
/* ################################################################################## */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#ifndef NOMPI
#include <mpi.h>
#endif
#include <signal.h>
#include <unistd.h>

//#include "allvars.hpp"
#include "proto.hpp"


/*! \file endrun.c
 *  \brief Termination of simulation
 *
 *  This file contains routines for termination of the simulation.
 */

/*!  This function aborts the simulations. If a single processors wants an
 *   immediate termination, the function needs to be called with ierr>0. A
 *   bunch of MPI-error messages may also appear in this case.  For ierr=0,
 *   MPI is gracefully cleaned up, but this requires that all processors
 *   call endrun().
 */

// adapted for AMUSE:
void gadgetmp2::endrun(int ierr)
{
  if(ierr)
    {
      printf("task %d: endrun called with an error level of %d\n\n\n", ThisTask, ierr);
      fflush(stdout);
    }
  exit(0);
}

