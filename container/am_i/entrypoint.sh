#!/bin/bash -e
main() {
    case "$1" in
        root)
            if am_i_"$1"; then
                echo YES
            else
                echo NO
                exit 1
            fi
            ;;
        *)
            echo NO
            exit 1
            ;;
    esac
}

am_i_root() {
    (( UID == 0 ))
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
