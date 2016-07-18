// This script iterates over the list of jenkins jobs and updates the
// TARGET_JOBS job parameter with the jobs matching the job_pattern

import hudson.model.*
import java.util.Collections

// Retrieve the version parameters chosen in the current build
def version = build.buildVariableResolver.resolve('TARGET_VERSION')

target_jobs_lst = []

// get a list of the relevant build-artifacts-manual jobs for project+version
def job_pattern = ~/^{project}_${{version}}_build-artifacts-manual-.*$/
hudson.model.Hudson.instance.items.findAll{{job -> job}}.each {{
job ->
  if ((job.name ==~ job_pattern) && !job.isDisabled()){{
    target_jobs_lst.add(job.name)
  }}
}}
def target_jobs_str = target_jobs_lst.join(',')
println("Target jobs to run: " + target_jobs_str)

// Update the job's TARGET_JOBS parameter for later use
// Reference:
// https://groups.google.com/forum/#!topic/jenkinsci-users/szhuDfCvpiE
// This code will probably need to change once we upgrade to new jenkins:
// https://issues.jenkins-ci.org/browse/JENKINS-35377
def targer_jobs_sp = new StringParameterValue('TARGET_JOBS', target_jobs_str)
def newPa = null
def oldPa = build.getAction(ParametersAction.class)
if (oldPa != null) {{
  build.actions.remove(oldPa)
  newPa = oldPa.createUpdated(Collections.singleton(targer_jobs_sp))
}} else {{
  newPa = new ParametersAction(targer_jobs_sp)
}}
build.actions.add(newPa)
