// standard-webhook-trigger.groovy - Trigger other jobs based on information
//                                   posted to the webhook
//
def main() {
    def job_data
    stage("Load WebHook data") {
        job_data = detect_github_event()
    }
    if(!job_data) {
        return
    }
    stage("Launching Job") {
        job_data.wait = false
        try {
            build job_data
        } catch(hudson.AbortException e) {
            echo "Launching job failed, it probably does not exist"
            currentBuild.result = 'NOT_BUILT'
        }
    }
}

def detect_github_event() {
    if(!params.x_github_event) {
        return
    }
    String event = "${params.x_github_event} [${params.x_github_delivery}]"
    String org = params.GH_EV_REPO_owner_login
    String repo = params.GH_EV_REPO_name
    String branch = params.GH_EV_REF.tokenize('/')[-1]
    echo "Detected GitHub event: $event\nTo: $org/$repo/$branch"
    currentBuild.description = "$event\nTo: $org/$repo/$branch"
    if(params.x_github_event == 'push') {
        echo "Found GitHub push event"
        String job = "${org}_${repo}_standard-on-ghpush"
        echo "Will attempt to trigger job: $job"
        return [ job: job, parameters: get_job_parametes(), ]
    }
}

@NonCPS
def get_job_parametes() {
    [
        'x_github_event',
        'x_github_delivery',
        'GH_EV_REPO_name',
        'GH_EV_REPO_full_name',
        'GH_EV_REPO_owner_name',
        'GH_EV_REPO_owner_login',
        'GH_EV_REF',
        'GHPUSH_SHA',
        'GHPUSH_PUSHER_name',
        'GHPUSH_PUSHER_email',
        'GH_EV_HEAD_COMMIT_id',
        'GH_EV_HEAD_COMMIT_url'
    ].collect { string(name: it, value: params."$it") }
}

main()
