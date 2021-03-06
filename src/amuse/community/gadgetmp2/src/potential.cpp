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
#include <float.h>
#ifndef NOMPI
#include <mpi.h>
#endif


//#include "allvars.hpp"
#include "proto.hpp"


/*! \file potential.c
 *  \brief Computation of the gravitational potential of particles
 */


/*! This function computes the gravitational potential for ALL the particles.
 *  First, the (short-range) tree potential is computed, and then, if needed,
 *  the long range PM potential is added.
 */
void gadgetmp2::compute_potential(void)
{
    int i;

#ifndef NOGRAVITY
    long long ntot, ntotleft;
    int j, k, level, sendTask, recvTask;
    int ndone;
    int maxfill, ngrp, place, nexport;
    int *nsend, *noffset, *nsend_local, *nbuffer, *ndonelist, *numlist;
    my_float fac;
    double t0, t1, tstart, tend;
#ifndef NOMPI
    MPI_Status status;
#endif
    my_float r2;

    t0 = second();

    if(All.ComovingIntegrationOn)
        set_softenings();

    if(ThisTask == 0)
    {
        printf("Start computation of potential for all particles...\n");
        fflush(stdout);
    }


    tstart = second();
    if(TreeReconstructFlag)
    {
        if(ThisTask == 0)
            printf("Tree construction.\n");

        force_treebuild(NumPart);

        TreeReconstructFlag = 0;

        if(ThisTask == 0)
            printf("Tree construction done.\n");
    }
    tend = second();
    All.CPU_TreeConstruction += timediff(tstart, tend);

    numlist = new int[NTask * NTask];
#ifndef NOMPI
    MPI_Allgather(&NumPart, 1, MPI_INT, numlist, 1, MPI_INT, GADGET_WORLD);
#else
    numlist[0] = NumPart;
#endif
    for(i = 0, ntot = 0; i < NTask; i++)
        ntot += numlist[i];
    free(numlist);

    noffset = new int[NTask];	/* offsets of bunches in common list */
    nbuffer = new int[NTask];
    nsend_local = new int[NTask];
    nsend = new int[NTask * NTask];
    ndonelist = new int[NTask];

    i = 0;			/* beginn with this index */
    ntotleft = ntot;		/* particles left for all tasks together */

    while(ntotleft > 0)
    {
        for(j = 0; j < NTask; j++)
            nsend_local[j] = 0;

        /* do local particles and prepare export list */
        for(nexport = 0, ndone = 0; i < NumPart && nexport < All.BunchSizeForce - NTask; i++)
        {
            ndone++;

            for(j = 0; j < NTask; j++)
                Exportflag[j] = 0;

#ifndef PMGRID
            force_treeevaluate_potential(i, 0);
#else
            force_treeevaluate_potential_shortrange(i, 0);
#endif

            for(j = 0; j < NTask; j++)
            {
                if(Exportflag[j])
                {
                    /*		  for(k = 0; k < 3; k++)
                     *		    GravDataGet[nexport].u.Pos[k] = P[i].Pos[k];
                     */
                    //GravDataGet[nexport].u0 = P[i].Pos[0];
                    GravDataGet->set_init_u0(P[i].Pos[0],nexport);
                    //GravDataGet[nexport].u1 = P[i].Pos[1];
                    GravDataGet->set_init_u1(P[i].Pos[1],nexport);
                    //GravDataGet[nexport].u2 = P[i].Pos[2];
                    GravDataGet->set_init_u2(P[i].Pos[2],nexport);
#ifdef UNEQUALSOFTENINGS
                    //GravDataGet[nexport].Type = P[i].Type;
                    GravDataGet->set_Type(P[i].Type,nexport);
#ifdef ADAPTIVE_GRAVSOFT_FORGAS
                    if(P[i].Type == 0)
                        //GravDataGet[nexport].Soft = SphP[i].Hsml;
                        GravDataGet->set_init_Soft(SphP[i].Hsml,nexport);
#endif
#endif
                    //GravDataGet[nexport].OldAcc = P[i].OldAcc;
                    GravDataGet->set_init_OldAcc(P[i].OldAcc,nexport);

                    GravDataIndexTable[nexport].Task = j;
                    GravDataIndexTable[nexport].Index = i;
                    GravDataIndexTable[nexport].SortIndex = nexport;

                    nexport++;
                    nsend_local[j]++;
                }
            }
        }

        qsort(GravDataIndexTable, nexport, sizeof(struct gravdata_index), grav_tree_compare_key);

        for(j = 0; j < nexport; j++)
            //GravDataIn[j] = GravDataGet[GravDataIndexTable[j].SortIndex];
            gravdata_in::lcopy(GravDataIn, j, GravDataGet, GravDataIndexTable[j].SortIndex);

        for(j = 1, noffset[0] = 0; j < NTask; j++)
            noffset[j] = noffset[j - 1] + nsend_local[j - 1];

#ifndef NOMPI
        MPI_Allgather(nsend_local, NTask, MPI_INT, nsend, NTask, MPI_INT, GADGET_WORLD);
#else
        nsend[0] = nsend_local[0];
#endif
        /* now do the particles that need to be exported */

        for(level = 1; level < (1 << PTask); level++)
        {
            for(j = 0; j < NTask; j++)
                nbuffer[j] = 0;
            for(ngrp = level; ngrp < (1 << PTask); ngrp++)
            {
                maxfill = 0;
                for(j = 0; j < NTask; j++)
                {
                    if((j ^ ngrp) < NTask)
                        if(maxfill < nbuffer[j] + nsend[(j ^ ngrp) * NTask + j])
                            maxfill = nbuffer[j] + nsend[(j ^ ngrp) * NTask + j];
                }
                if(maxfill >= All.BunchSizeForce)
                    break;

                sendTask = ThisTask;
                recvTask = ThisTask ^ ngrp;

#ifndef NOMPI
                if(recvTask < NTask)
                {
                    if(nsend[ThisTask * NTask + recvTask] > 0 || nsend[recvTask * NTask + ThisTask] > 0)
                    {
                        /* get the particles */
                        MPI_Sendrecv(GravDataIn->get_buff_start(noffset[recvTask]),
                                     nsend_local[recvTask] * gravdata_in::get_size(), MPI_BYTE,
                                     recvTask, TAG_POTENTIAL_A,
                                     GravDataGet->get_buff_start(nbuffer[ThisTask]),
                                     nsend[recvTask * NTask + ThisTask] * gravdata_in::get_size(), MPI_BYTE,
                                recvTask, TAG_POTENTIAL_A, GADGET_WORLD, &status);
                    }
                }
#endif

                for(j = 0; j < NTask; j++)
                    if((j ^ ngrp) < NTask)
                        nbuffer[j] += nsend[(j ^ ngrp) * NTask + j];
            }

            for(j = 0; j < nbuffer[ThisTask]; j++)
            {
#ifndef PMGRID
                force_treeevaluate_potential(j, 1);
#else
                force_treeevaluate_potential_shortrange(j, 1);
#endif
            }


            /* get the result */
            for(j = 0; j < NTask; j++)
                nbuffer[j] = 0;
            for(ngrp = level; ngrp < (1 << PTask); ngrp++)
            {
                maxfill = 0;
                for(j = 0; j < NTask; j++)
                {
                    if((j ^ ngrp) < NTask)
                        if(maxfill < nbuffer[j] + nsend[(j ^ ngrp) * NTask + j])
                            maxfill = nbuffer[j] + nsend[(j ^ ngrp) * NTask + j];
                }
                if(maxfill >= All.BunchSizeForce)
                    break;

                sendTask = ThisTask;
                recvTask = ThisTask ^ ngrp;

#ifndef NOMPI
                if(recvTask < NTask)
                {
                    if(nsend[ThisTask * NTask + recvTask] > 0 || nsend[recvTask * NTask + ThisTask] > 0)
                    {
                        /* send the results */
                        MPI_Sendrecv(GravDataResult->get_buff_start(nbuffer[ThisTask]),
                                     nsend[recvTask * NTask + ThisTask] * gravdata_in::get_size(),
                                MPI_BYTE, recvTask, TAG_POTENTIAL_B,
                                GravDataOut->get_buff_start(noffset[recvTask]),
                                nsend_local[recvTask] * gravdata_in::get_size(),
                                MPI_BYTE, recvTask, TAG_POTENTIAL_B, GADGET_WORLD, &status);

                        /* add the result to the particles */
                        for(j = 0; j < nsend_local[recvTask]; j++)
                        {
                            place = GravDataIndexTable[noffset[recvTask] + j].Index;

                            //P[place].Potential += GravDataOut[j + noffset[recvTask]].u0;
                            P[place].Potential += GravDataOut->read_re_init_u0(j + noffset[recvTask]);
                        }
                    }
                }
#endif
                for(j = 0; j < NTask; j++)
                    if((j ^ ngrp) < NTask)
                        nbuffer[j] += nsend[(j ^ ngrp) * NTask + j];
            }

            level = ngrp - 1;
        }

#ifndef NOMPI
        MPI_Allgather(&ndone, 1, MPI_INT, ndonelist, 1, MPI_INT, GADGET_WORLD);
#else
        ndonelist[0] = ndone;
#endif // NOMPI
        for(j = 0; j < NTask; j++)
            ntotleft -= ndonelist[j];
    }

    free(ndonelist);
    free(nsend);
    free(nsend_local);
    free(nbuffer);
    free(noffset);


    /* add correction to exclude self-potential */

    for(i = 0; i < NumPart; i++)
    {
        /* remove self-potential */
        P[i].Potential += P[i].Mass / All.SofteningTable[P[i].Type];

        if(All.ComovingIntegrationOn)
            if(All.PeriodicBoundariesOn)
                P[i].Potential -= 2.8372975 * pow(P[i].Mass, 2.0 / 3) *
                        std::pow(All.Omega0 * 3 * All.Hubble * All.Hubble / (8 * const_PI.toDouble() * All.G), 1.0 / 3);
    }


    /* multiply with the gravitational constant */

    for(i = 0; i < NumPart; i++)
        P[i].Potential *= All.G;


    if(All.ComovingIntegrationOn)
    {
#ifndef PERIODIC
        fac = -0.5 * All.Omega0 * All.Hubble * All.Hubble;

        for(i = 0; i < NumPart; i++)
        {
            for(k = 0, r2 = 0; k < 3; k++)
                r2 += P[i].Pos[k] * P[i].Pos[k];

            P[i].Potential += fac * r2;
        }
#endif
    }
    else
    {
        fac = -const_0_5 * All.OmegaLambda * All.Hubble * All.Hubble;
        if(fac != const_0)
        {
            for(i = 0; i < NumPart; i++)
            {
                for(k = 0, r2 = 0; k < 3; k++)
                    r2 += P[i].Pos[k] * P[i].Pos[k];

                P[i].Potential += fac * r2;
            }
        }
    }


    if(ThisTask == 0)
    {
        printf("potential done.\n");
        fflush(stdout);
    }

    t1 = second();

    All.CPU_Potential += timediff(t0, t1);

#else
    for(i = 0; i < NumPart; i++)
        P[i].Potential = const_0;
#endif
}
