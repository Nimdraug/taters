# taters

## What's taters, eh?

The Red Book of Westmarch has this to say about taters (taken from a lengthy section about various foods in middle-earth,
commonly thought to have been added by Samwise Gamgee, Mayor of the Shire):

> Taters, or Potatoes as they are also known, are a most versatile crop. Boil 'em, Mash 'em, stick 'em in a stew.
> Aye, they even go well as chips. This most exquisite tuber will make a fine addition to any meal.

What you have in front of you, however, is something completely different...

Taters is a python-based fully modular build and deployment framework. It was primarily created to help automate
common web-development tasks, but is flexible enough to be useful in other scenarios.

For instance, if you want to copy all the files from one directory to another, you would do this:

```python
import taters.locations

taters.locations.local( 'some-other-dir' ).destination(
    taters.locations.local( '.' ).source( recursive = True ), 
    overwrite = True
)
```

Or if you have a website and you want to build it and then deploy it to an ftp server all in one go, then you can do this:

```python
import taters.locations

def build( files ):
    for f in files:
        if f.name.endswith( '.less' ):
            yield taters.lessc( taters.lazy_file( 'less/styles.less' ), include_path = 'less/' ).rename( 'styles.css' )
        elif f.name.endswith( '.js' ):
            yield taters.uglifyjs( [ 'js/library-1.js', 'js/library-2.js', 'js/main.js' ] ).rename( 'site.min.js' )
        else:
            yield f

taters.locations.ftp( 'ftp://user:password@example.tld/public_html/' ).destination(
    build(
        taters.locations.local( '.' ).source( recursive = True )
    ),
    overwrite = True
)
```

## Installation

To install the latest (dev) version first clone this repository using git:

```sh
git clone https://github.com/Nimdraug/taters.git
```

then install the library using the setup.py script

```sh
python setup.py install
```

and then run the post-install.sh script to ensure you have the required node.js modules (less and uglifyjs):

```sh
./post-install.sh
```

## Here be dragons

Please note that taters is currently in alpha development phase. Meaning that things can change at any moment
as the code evolves. It is, however, used in live situations and will therefore remain fairly stable.

So feel free to use this in your projects, but just beware, and please [report any bugs](https://github.com/Nimdraug/taters/issues) you might encounter.
