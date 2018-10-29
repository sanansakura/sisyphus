import os
import re

# Inputs directories
LUSTRE_ARCHIVE = os.path.join('/', 'share', 'lustre', 'archive')
SHAHLAB_ARCHIVE = os.path.join('/', 'shahlab', 'archive')
NEXTSEQ_ARCHIVE = os.path.join(SHAHLAB_ARCHIVE, 'single_cell_indexing', 'NextSeq')
BCL_DIR = os.path.join(NEXTSEQ_ARCHIVE, 'bcl', '{run_id}')
FASTQ_DIR = os.path.join(NEXTSEQ_ARCHIVE, 'fastq', '{run_id}')

# Shahlab directories
SHAHLAB_PIPELINE_DIR = os.path.join('{jobs_dir}', '{jira}{tag}')
SHAHLAB_RESULTS_DIR = os.path.join('{jobs_dir}', '{jira}{tag}', 'results')
SHAHLAB_TMP_DIR = os.path.join('{jobs_dir}', '{jira}{tag}', 'temp')

# Azure directories
AZURE_PIPELINE_DIR = os.path.join('/', 'datadrive', 'pipeline', '{jira}{tag}')
# Note: pipeline results are created in the working directory, not on blob
# eventually we want to fix this but it will require some major refactoring
AZURE_SCPIPELINE_DIR = os.path.join('singlecelldata', 'pipeline', '{jira}{tag}')
AZURE_RESULTS_DIR = os.path.join('singlecelldata', 'results', '{jira}{tag}', 'results')
AZURE_TMP_DIR = os.path.join('singlecelldata', 'temp', '{jira}{tag}')

# Results directories
SFTP_RESULTS_DIR = os.path.join('/', 'projects', 'sftp', 'shahlab', 'singlecell', '{jira}')
BLOB_RESULTS_DIR = os.path.join('{jira}')  # results container in the singlecelldata storage account
MT_BAMS_DIR = os.path.join('single_cell_indexing', 'bam', '{chip_id}', '{ref_genome}', '{aligner}-MT')

ALIGNMENT_RESULTS = os.path.join('{results_dir}', 'alignment')
HMMCOPY_RESULTS = os.path.join('{results_dir}', 'hmmcopy_autoploidy')


# Regular expressions
LIBRARY_ID_RE = re.compile("^[IP]X[0-9]+$")
LANE_ID_RE = re.compile("^.*_\\d$")
JIRA_ID_RE = re.compile('^SC-[0-9]+$')

BRC_SOURCE_RE_LIST = [
    re.compile("^http://bigwigs.brc.ubc.ca/sequencing.*/(\\d{6}_[A-Z0-9]+_\\d{4}_([A-Z0-9]+))/$"),
    re.compile("^beast:/.*/(\\d{6}_[A-Z0-9]+_\\d{4}_([A-Z0-9]+))/$"),
    re.compile("^patientdata@brclogin1.brc.ubc.ca:/.*/(\\d{6}_[A-Z0-9]+_\\d{4}_([A-Z0-9]+))/$"),
]

ALIGNMENT_METRICS = os.path.join(
	'{results_dir}',
	'results',
	'alignment',
	'{library_id}_alignment_metrics.h5'
)

BAM_TEMPLATE = os.path.join(
	'single_cell_indexing',
	'bam',
	'{library_id}',
	'{ref_genome}',
	'{aligner_name}',
	'numlanes_{number_lanes}',
	'{cell_id}.bam'
)

SHAHLAB_BAM_TEMPLATE = os.path.join(SHAHLAB_ARCHIVE, BAM_TEMPLATE)
AZURE_BAM_TEMPLATE = os.path.join('singlecelldata', 'data', BAM_TEMPLATE)
