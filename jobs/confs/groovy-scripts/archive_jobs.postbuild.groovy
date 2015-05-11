import org.jvnet.hudson.plugins.groovypostbuild.*

def goodRow(job_name, new_job_info) {
    def new_job_name = new_job_info[0]
    def new_job_url = new_job_info[1]
    row = "<tr><td bgcolor=\"#3BA6FE\"><b>$job_name</b>"
    row += "</td><td bgcolor=\"#4DDC37\"><b>$new_job_name (<a href=\"$new_job_url\">$new_job_url</a>)</b></td></tr>"
    return row
}

def badRow(job_name) {
    row = "<tr><td bgcolor=\"#FDFD2C\"><b>$job_name</b>"
    row += "</td><td bgcolor=\"#FE3B3B\"><b>" +
            "Requested job not found, something really strange is going on as this should never happen" +
            "</b></td></tr>"
    return row
}

err_pattern = ~/.*ERROR:: Requested job (.+) not found, something really strange is going on as this should never happen.*/
good_pattern = ~/.*INFO:: Updating job: (.+) --> (.+) \((.+)\)/
def job_status_map = [:]
manager.build.logFile.eachLine { line ->
    good_matcher = good_pattern.matcher(line)
    err_matcher = err_pattern.matcher(line)
    if (good_matcher.matches()) {
        jobName = good_matcher.group(1)
        job_status_map[jobName] = [good_matcher.group(2), good_matcher.group(3)]
    } else if (err_matcher.matches()) {
        jobName = err_matcher.group(1)
        job_status_map[jobName] = []
    }
}


if(job_status_map.size() > 0) {
    summary = manager.createSummary('document.gif')
    summary.appendText(
            "<table>" +
                    "<tr>" +
                    "<th colspan=\"2\" bgcolor=\"#EEEEEE\">Archived Jobs</th>" +
                    "</tr>" +
                    "<tr>" +
                    "<th bgcolor=\"#EEEEEE\">Original Name</th>" +
                    "<th bgcolor=\"#EEEEEE\">New Name</th>" +
                    "</tr>",
            false
    )
    job_status_map.each { job_info ->
        if (job_info.value.isEmpty()) {
            summary.appendText(badRow(job_info.key), false)
        } else {
            summary.appendText(goodRow(job_info.key, job_info.value), false)
        }
    }
    summary.appendText("</table>", false)
}
