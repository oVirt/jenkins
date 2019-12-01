// email_notify.groovy - Function to send emails.
//
def email_notify(status, recipients='infra@ovirt.org') {
    emailext(
        subject: "[oVirt Jenkins] ${env.JOB_NAME}" +
            " - Build #${env.BUILD_NUMBER} - ${status}!",
        body: [
            "Build: ${env.BUILD_URL}",
            "Build Name: ${currentBuild.displayName}",
            "Build Status: ${status}",
            "Gerrit change: ${params.GERRIT_CHANGE_URL}",
            "- title: ${params.GERRIT_CHANGE_SUBJECT}",
            "- project: ${params.GERRIT_PROJECT}",
            "- branch: ${params.GERRIT_BRANCH}",
            "- author: ${params.GERRIT_CHANGE_OWNER_NAME}" +
            " <${params.GERRIT_CHANGE_OWNER_EMAIL}>",
        ].join("\n"),
        to: recipients,
        mimeType: 'text/plain'
    )
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this