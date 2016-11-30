#!/bin/bash -e
# bash wrapper around duplicity

readonly LOCK_DIR=/tmp/lock/jenkins-backuper/locker
readonly DEFAULT_FULL="1m"
readonly DEFAULT_TOKEEP="180D"
readonly DEFAULT_VERBOSITY="8"

print_usage()
{
    echo "\
        duplicity-backup.sh : duplicity wrapper
        --ssh  site         : remote backup site
        --full days         : do a full backup each X times(default=$DEFAULT_FULL)
        --tokeep days       : days to keep(default=$DEFAULT_TOKEEP)
        --exclude glob      : comma seperated of globes to exclude from backup
        --backup_dir dir    : directory to backup
        --logfile log       : log location(defaults to working directory)
        --verbosity [1-9]   : verbosity level(default=$DEFAULT_VERBOSITY)
        check out 'man duplicity' for more details
    "
}

parse_args()
{
    readonly script_name="$(basename "$0")"
    while [[ $# -gt  0 ]]
    do
        key="$1"
        case $key in
            --ssh)
                readonly REMOTE_SSH="$2"
                shift
                ;;
            --backup_dir)
                readonly BACKUP_DIR="$2"
                shift
                ;;
            --full)
                FULL="$2"
                shift
                ;;

            --tokeep)
                TOKEEP="$2"
                shift
                ;;
            --logfile)
                LOG_FILE="$2"
                shift
                ;;
            --exclude)
                readonly EXCLUDE_RAW="$2"
                shift
                ;;
            --verbosity)
                readonly VERBOSITY="$2"
                shift
                ;;
            -h|--help)
                print_usage
                ;;
            *)
                break
        esac
        shift
    done
    local working_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    if [[ -z "$REMOTE_SSH" ]]; then
        print_usage
        echo "missing --ssh parameter, exiting"
        exit 1
    fi
    if [[ -z "$BACKUP_DIR" ]]; then
        echo "missing --backup_dir parameter, exiting"
        exit 1
    fi
    if [[ -z "$FULL" ]]; then
        readonly FULL="$DEFAULT_FULL"
        echo "using default: full = $FULL"
    fi
    if [[ -z "$TOKEEP" ]]; then
        readonly TOKEEP="$DEFAULT_TOKEEP"
        echo "using default: tokeep = $TOKEEP"
    fi
    if [[ -z "$LOG_FILE" ]]; then
        readonly LOG_FILE="$working_dir/$script_name.log"
        echo "using default: log_file = $LOG_FILE"
    fi
    if [[ -z "$VERBOSITY" ]]; then
        readonly VERBOSITY="$DEFAULT_VERBOSITY"
        echo "using default: verbosity = $VERBOSITY"
    fi

    if ! mkdir -p $LOCK_DIR; then
        echo "already running, if this is untrue delete $LOCK_DIR"
        exit 1
    fi
    if ! command -v duplicity >/dev/null 2>&1; then
        echo "duplicity package not found, exiting"
        exit 1
    fi

    if [[ -z "$WORKSPACE" ]]; then
        readonly WORKSPACE="$working_dir"
    fi

}

create_exclude()
{
    rm -f "$WORKSPACE"/exclude_list
    if  ! [[ -z "$EXCLUDE_RAW" ]]; then
        set -f && IFS=',' &&  for excluder in $EXCLUDE_RAW; do
            echo "- $BACKUP_DIR/$excluder" >> "$WORKSPACE/exclude_list"
        done && set +f
    fi
}



exit_program()
{
    rm -rf $LOCK_DIR

}

eval_print()
{
    printf '*%.0s' {1..80}; echo
    echo "executing: $1"
    printf '*%.0s' {1..80}; echo
    eval "$1"
}

main()
{
    trap exit_program TERM QUIT INT HUP
    parse_args "$@"
    create_exclude
    arguments="incr --verbosity=$VERBOSITY --no-encryption "
    arguments+="--full-if-older-than=$FULL "
    if ! [[ -z "$EXCLUDE_RAW" ]]; then
        arguments+="--exclude-globbing-filelist=$WORKSPACE/exclude_list "
    fi
    arguments+="--log-file=$LOG_FILE $BACKUP_DIR $REMOTE_SSH "

    # https://github.com/paramiko/paramiko/issues/49
    # this is mostly relevant for CentOS 6
    paramiko_ver=$(rpm -qa | grep -e python.*-paramiko)
    if [[ "$paramiko_ver" =~ python-paramiko-1.7.5* ]]; then
        arguments+="--ssh-backend pexpect "
    fi
    eval_print "duplicity collection-status $REMOTE_SSH"
    eval_print "duplicity $arguments"
    eval_print "duplicity remove-older-than --no-encryption --force $TOKEEP $REMOTE_SSH"
    eval_print "duplicity cleanup --no-encryption --force $REMOTE_SSH"
    eval_print "duplicity collection-status $REMOTE_SSH"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
