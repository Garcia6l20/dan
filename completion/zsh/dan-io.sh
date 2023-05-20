#compdef dan-io

_dan_io_completion() {
    local -a completions
    local -a completions_with_descriptions
    local -a response
    (( ! $+commands[dan-io] )) && return 1

    response=("${(@f)$(env COMP_WORDS="${words[*]}" COMP_CWORD=$((CURRENT-1)) _DAN_IO_COMPLETE=zsh_complete 'dan-io')}")

    for type key descr in ${response}; do
        if [[ "$type" =~ ^(plain|nospace)$ ]]; then
            if [[ "$descr" == "_" ]]; then
                completions+=("$key")
            else
                completions_with_descriptions+=("$key":"$descr")
            fi
        elif [[ "$type" == "dir" ]]; then
            _path_files -/
        elif [[ "$type" == "file" ]]; then
            _path_files -f
        fi
    done

    if [ -n "$completions_with_descriptions" ]; then
        _describe -V unsorted completions_with_descriptions -U
    fi

    if [ -n "$completions" ]; then
        if [[ "$type" == "nospace" ]]; then
            compadd -U -S '' -V unsorted -a completions
        else
            compadd -U -V unsorted -a completions
        fi
    fi
}

compdef _dan_io_completion dan-io;

