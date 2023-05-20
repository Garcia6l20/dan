_dan_completion() {
    local IFS=$'\n'
    local response

    response=$(env COMP_WORDS="${COMP_WORDS[*]}" COMP_CWORD=$COMP_CWORD _DAN_COMPLETE=bash_complete $1)

    for completion in $response; do
        IFS=',' read type value <<< "$completion"

        if [[ $type == 'dir' ]]; then
            COMPREPLY=()
            compopt -o dirnames
        elif [[ $type == 'file' ]]; then
            COMPREPLY=()
            compopt -o default
        elif [[ $type == 'plain' ]]; then
            COMPREPLY+=($value)
        elif [[ $type == 'nospace' ]]; then
            COMPREPLY+=($value)
            compopt -o nospace
        fi
    done

    return 0
}

_dan_completion_setup() {
    complete -o nosort -F _dan_completion dan
}

_dan_completion_setup;

