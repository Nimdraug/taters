#!/bin/sh
# Installs non-python requirements for taters

# Ensure npm is available and give error if not
if type npm &> /dev/null
then
    # Install less if not already intalled
    echo -n 'Checking for less... '
    if ! npm --global info less &> /dev/null
    then
        echo 'Installing!'
        npm --global install less
    else
        echo 'Found!'
    fi

    # Install uglifyjs if not already intalled
    echo -n 'Checking for uglifyjs... '
    if ! npm --global info uglifyjs &> /dev/null
    then
        echo 'Installing!'
        npm --global install uglifyjs
    else
        echo 'Found!'
    fi
else
    >&2 echo "Could not find npm! Please install it (See https://www.npmjs.com/get-npm) and run this script again."
    exit 1
fi
