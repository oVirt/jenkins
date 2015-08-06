// Groovy script to disable & rename jobs meant for deletion ( = removed from YAML )

import hudson.model.*
import jenkins.model.*

String workspace = build.workspace.toString()
File jobsFile = new File( workspace + "/xml_diff.txt" )
boolean archive_jobs = build.buildVariableResolver.resolve("ARCHIVE_JOBS").toString().toBoolean()

if( !jobsFile.exists() ) {
    println "Jobs file " + jobsFile.getAbsolutePath() + " does not exist"
} else {
    jobsFile.eachLine { line ->
        def job_name = line.trim()
        if (job_name) { // ignore empty lines
            def job = Jenkins.instance.getItem(job_name)
            if ( !job ) {
                println("ERROR:: Requested job ${job_name} not found, something really strange is going on as this should never happen")
            } else {
                new_job_name = job.name + "_archived_for_deletion"
                if (archive_jobs) {
                    print("INFO:: Updating job: ${job.name} --> ")
                    job.disable()
                    job.renameTo(new_job_name)
                    println("${job.name} (${job.getAbsoluteUrl()})")
                } else {
                    println("INFO:: Dry Run: ${job.name} --> ${new_job_name}")
                }
            }
        }
    }
}
