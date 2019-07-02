// gate.groovy - System pathc gating job

def main() {
    stage('check commits') {
        print "Going to check the following commits\n$CHECKED_COMMITS"
    }
}

// We need to return 'this' so the actual pipeline job can invoke functions from
// this script
return this
