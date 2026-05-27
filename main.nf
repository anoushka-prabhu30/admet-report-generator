#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

/*
 * ADMET Drug Report Generator
 *
 * Stage each Python script as  bin/<name>.py  in the task work directory so
 * os.path.dirname(__file__) resolves to  <workdir>/bin/  and the scripts'
 * ../data/ and ../output/ paths land correctly inside the work directory.
 */

// ─── Processes ──────────────────────────────────────────────────────────────

process FETCH {
    container 'python:3.11'

    input:
    path 'bin/fetch.py'

    output:
    path 'data/compounds.csv', emit: compounds

    script:
    """
    pip install --quiet --no-cache-dir pandas chembl-webresource-client
    mkdir -p data
    python bin/fetch.py
    """
}

process FEATURIZE {
    container 'python:3.11'

    input:
    path 'bin/featurize.py'
    path 'data/compounds.csv'

    output:
    path 'data/compounds_featurized.csv', emit: featurized

    script:
    """
    pip install --quiet --no-cache-dir pandas numpy rdkit
    python bin/featurize.py
    """
}

process PREDICT {
    container 'python:3.11'

    input:
    path 'bin/predict.py'
    path 'data/compounds_featurized.csv'

    output:
    path 'data/compounds_admet.csv', emit: admet

    script:
    """
    pip install --quiet --no-cache-dir pandas numpy admet-ai
    python bin/predict.py
    """
}

process NARRATE {
    container 'python:3.11'

    input:
    path 'bin/narrate.py'
    path 'data/compounds_admet.csv'

    output:
    path 'data/compounds_narrated.csv', emit: narrated

    script:
    """
    export GEMINI_API_KEY=${System.getenv('GEMINI_API_KEY') ?: ''}
    pip install --quiet --no-cache-dir pandas google-generativeai
    python bin/narrate.py
    """
}

process REPORT {
    container 'python:3.11'
    publishDir "${projectDir}/output", mode: 'copy'

    input:
    path 'bin/report.py'
    path 'data/compounds_narrated.csv'
    path 'templates/report.html.j2'

    output:
    path 'output/report.html', emit: html

    script:
    """
    pip install --quiet --no-cache-dir pandas numpy plotly jinja2 scipy
    mkdir -p output
    python bin/report.py
    """
}

// ─── Workflow ────────────────────────────────────────────────────────────────

workflow {
    fetch_script    = Channel.fromPath("${projectDir}/bin/fetch.py")
    featurize_script = Channel.fromPath("${projectDir}/bin/featurize.py")
    predict_script   = Channel.fromPath("${projectDir}/bin/predict.py")
    narrate_script   = Channel.fromPath("${projectDir}/bin/narrate.py")
    report_script    = Channel.fromPath("${projectDir}/bin/report.py")
    template         = Channel.fromPath("${projectDir}/templates/report.html.j2")

    FETCH(fetch_script)
    FEATURIZE(featurize_script, FETCH.out.compounds)
    PREDICT(predict_script, FEATURIZE.out.featurized)
    NARRATE(narrate_script, PREDICT.out.admet)
    REPORT(report_script, NARRATE.out.narrated, template)

    REPORT.out.html | view { "Report ready: $it" }
}
