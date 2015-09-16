#! /usr/bin/python
"""

Calculate coverage


"""

import sys
import os
from datetime import datetime
import argparse
import subprocess
import multiprocessing
import numpy

from bedparse import BedExtract

#
# Subroutines
#

def PrintHeader( myself, arg ):
    now = datetime.now()

    print '#' * 84
    print '# Summary'
    print '# Generated by %(my)s' % { 'my': myself }
    print '# %(y)d.%(m)d.%(d)d.%(h)d:%(m)d' % { 'y': now.year, 'm': now.month, 'd': now.day, 'h': now.hour, 'm': now.minute }
    print '#' * 84 + ''
    print '# input_bam:\t{0} '.format( arg.input_bam )
    print '# coverage_tmp:\t{0} '.format( arg.coverage_tmp )
    print '# genome_bed:\t{0} '.format( arg.genome_bed )
    print '# bin_size:\t{0} '.format( arg.bin_size )
    print '# sample_num:\t{0} '.format( arg.sample_num )
    print '# samtools:\t{0} '.format( arg.samtools )
    print '# coverage_depth:\t{0} '.format( arg.coverage_depth )
    print '# process:\t{0} '.format( arg.process )

def depth_b_worker( samtools, bam, bed, output_file ):

    samtools_cmd = '{samtools} depth -b {bed} {bam} > {out}'.format(samtools = samtools, bed = bed, bam = bam, out = output_file )
                  
    process = subprocess.Popen( samtools_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
                                
    std_out, std_err = process.communicate()
    p_return_code = process.returncode
            
def depth_r_worker( samtools, bam, bed, output_file ):
    f = open(bed, 'r')
    
    if os.path.exists(output_file):
        os.remove(output_file)
        
    for line in f:
        data = line.split( "\t" )
        samtools_cmd = '{samtools} depth -r {c}:{s}-{e} {bam} >> {out}'.format(
                        samtools = samtools, c = data[0], s = data[1], e = data[2].rstrip("\r\n"), bam = bam, 
                        out = output_file )
        ret = subprocess.check_call( samtools_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
    f.close()

 
#
# Main
#
def main():

#
# Argument parse
#
    argvs = sys.argv
    myself = argvs[ 0 ]

    parser = argparse.ArgumentParser( description = "Calculate coverage" )
    parser.add_argument( '-i', '--input_bam', help = "Input BAM file", type = str )
    parser.add_argument( '-t', '--coverage_tmp', help = "Temporary output file", type = str, default = './tmp.txt' )
    parser.add_argument( '-e', '--genome_bed', help = "Genome bed file", type = str, default = None)
    parser.add_argument( '-b', '--bin_size', help = "Length of samples to pick", type = int, default = 1000 )
    parser.add_argument( '-n', '--sample_num', help = "Number of samples to pick", type = int, default = 1000 )
    parser.add_argument( '-s', '--samtools', help = "Path to samtools", type = str, default = '/home/w3varann/tools/samtools-1.2/samtools' )
    parser.add_argument( '-c', '--coverage_depth', help = "List of coverage depth", type = str, default = '2,10,20,30,40,50,100' )
    parser.add_argument( '-p', '--process', help = "Number of processes to run ", type = int,  default = 10 )

    arg = parser.parse_args()
    if not arg.input_bam:
        print parser.print_help();
        sys.exit( 1 )

    if arg.genome_bed == None:
        print "Not yet support to WGS... :("
        sys.exit(1)
        
    #
    # Print header
    #
    PrintHeader( myself, arg )

    try:
        #
        # Parse genomesize file
        #
        gen_bed = BedExtract( arg.genome_bed, arg.bin_size )

        #
        # Make index file if not exist
        #
        if not os.path.exists( arg.input_bam + '.bai' ):
            samtools_cmd = '{samtools} index {bam}'.format( samtools = arg.samtools, bam = arg.input_bam )
            process = subprocess.Popen( samtools_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
            std_out, std_err = process.communicate()
            p_return_code = process.returncode

        #
        # Run samtools mpileup
        #
        jobs = []
        if arg.process == 1:
            # create random sampling bed
            random_bed = arg.coverage_tmp + "0" + ".bed"
            gen_bed.save_random_bed( random_bed, arg.sample_num)

            depth_file = arg.coverage_tmp + '0'

            depth_r_worker( arg.samtools,  arg.input_bam, random_bed, depth_file )
        else:
            for i in range( 0, arg.process ):
                # create random sampling bed
                random_bed = arg.coverage_tmp + str( i ) + ".bed"
                gen_bed.save_random_bed( random_bed, arg.sample_num)
                depth_file = arg.coverage_tmp + str( i )

                process = multiprocessing.Process(
                        target = depth_r_worker,
                        args = ( arg.samtools, arg.input_bam, random_bed, depth_file )
                        )
                process.start()
                jobs.append( process )

            while len( jobs ) >= 1:
                j = jobs.pop()
                j.join()

        #
        # Calculate coverage
        #
        total_cov = 0
        sum = 0
        coverage = {}
        depth = []

        for i in range( 0, arg.process ):
            depth_file = arg.coverage_tmp + str( i )
            random_bed = arg.coverage_tmp + str( i ) + ".bed"

            f = open( depth_file )
            for line in f:
                line_list = line.split( "\t" )
                total_cov += 1
                sum += int( line_list[ 2 ] )
                depth.append(int( line_list[ 2 ] ))

                for num in arg.coverage_depth.split( ',' ):
                    if int( line_list[ 2 ] ) >= int( num ):
                        if num in coverage:
                            coverage[ num ] += 1
                        else:
                            coverage[ num ] = 1

            os.remove( depth_file )
            os.remove( random_bed )
            f.close()

        ave = numpy.average(depth)
        std = numpy.std(depth)

        #
        # Output result
        #
        data_string =  "non-N_total_depth\tnon-N_bases\taverage_depth\tdepth_stdev"
        for num in arg.coverage_depth.split( ',' ):
            data_string += "\t{0}x\t{0}x_ratio".format( num )

        print data_string

        data_string = "{0}\t{1}\t{2}\t{3}".format( sum, total_cov, ave, std )
        
        if len(coverage) == 0:
            print "no coverage data."
            return 0

        for cov_tmp in arg.coverage_depth.split( ',' ):
            if cov_tmp in coverage:
                data_string += "\t{num}\t{ratio}".format(
                                num = coverage[ cov_tmp ],
                                ratio = float( coverage[ cov_tmp ] )/ float( total_cov ) if coverage[ cov_tmp ] > 0 else 0 )
            else:
                data_string += "\t0\t0"

        print data_string

    except Exception:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print( "Unexpected error: {error}".format( error = sys.exc_info()[0] ) )
        print("{0}: {1}:{2}".format( exc_type, fname, exc_tb.tb_lineno) )



if __name__ == "__main__":
    main()

