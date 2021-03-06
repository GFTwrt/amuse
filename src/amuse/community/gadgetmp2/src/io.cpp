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
#include <errno.h>

#ifdef HAVE_HDF5
#include <hdf5.h>
#endif

//#include "allvars.hpp"
#include "proto.hpp"



/*! \file io.c
 *  \brief Routines for producing a snapshot file on disk.
 */

static int n_type[6];
static long long ntot_type_all[6];

/*! This catches I/O errors occuring for my_fwrite(). In this case we
 *  better stop.
 */
size_t gadgetmp2::my_fwrite(void *ptr, size_t size, size_t nmemb, FILE * stream)
{
  size_t nwritten;

  if((nwritten = fwrite(ptr, size, nmemb, stream)) != nmemb)
    {
      printf("I/O error (fwrite) on task=%d has occured: %s\n", ThisTask, strerror(errno));
      fflush(stdout);
      endrun(777);
    }
  return nwritten;
}

