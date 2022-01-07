# Instructions for using this code in another bot, or for re-releasing at a later point

At present, this bot uses docker and heroku to run the bot 24/7.

The heroku CLI (which is required for this), can be downloaded [here](https://devcenter.heroku.com/articles/heroku-cli).

For a more detailed guide on how to set this all up, please see - https://linuxtut.com/en/1b72bd2084a3f0c2e2a4/.

## Quick Notes on getting this up and running

### Using base heroku
1) Log into heroku and create a new app.
2) Go to settings > Buildpacks and add:
```
https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git
heroku/python
```
3) Under Config Vars, add a key named **_TOKEN_** and then enter your discord bot token as the value
4) Connect it up to github under the _deploy_ tab
5) Turn the bot on under **_Resources_**
6) Wait and see if it wants to work...
 
### Using Docker
Once you've got the heroku CLI installed and running, cd into the python repository that contains this code.

From there:
```
# login to container registry (should tell you that Login Succeeded)
heroku container:login

create your heroku app
heroku create <app_name>

# set discord TOKEN
heroku config:set TOKEN=hogehoge

# create and push your dockerfile to heroku
heroku container:push web --app <name_of_app>

# release the image
heroku container:release web --app <name_of_app>

# open your app to check it's running through:
heroku open --app <name_of_app>
```

## Running from docker
This is far simpler as it only involves faffing around with docker.

Simply run:
```
docker build --tag <name> .
docker run -e TOKEN=<paste_token> -d <name>
```
