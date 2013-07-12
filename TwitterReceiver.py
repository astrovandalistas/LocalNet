# -*- coding: utf-8 -*-

from interfaces import MessageReceiverInterface
from twython import Twython
from peewee import *
from json import loads, dumps
from threading import Thread
from time import time, strftime, localtime

class TwitterReceiver(MessageReceiverInterface):
    """A class for receiving Twitter messages and passing them to its
    subscribers"""
    ## How often to check twitter (in seconds)
    TWITTER_CHECK_PERIOD = 6
    ## What to search for
    SEARCH_TERMS = ["#aeLab", "#aeffect"]

    ## setup twitter connection and internal variables
    def setup(self, db, osc, loc):
        self.database = db
        self.oscClient = osc
        self.location = loc
        self.name = "twitter"
        self.lastTwitterCheck = time()
        self.mTwitter = None
        self.twitterAuthenticated = False
        self.largestTweetId = 1
        self.twitterResults = None
        self.hashTags = TwitterReceiver.SEARCH_TERMS
        ## read secrets from file
        inFile = open('oauth.txt', 'r')
        self.secrets = {}
        for line in inFile:
            (k,v) = line.split()
            self.secrets[k] = v
        self._authenticateTwitter()
        ## get largest Id for tweets that came before starting the program
        self._searchTwitter()
        self._getLargestTweetId()
        self.twitterResults = None
        ## return
        return True

    ## check for new tweets every once in a while
    def update(self):
        if (time() - self.lastTwitterCheck > TwitterReceiver.TWITTER_CHECK_PERIOD):
            self._searchTwitter()
            if (not self.twitterResults is None):
                for tweet in self.twitterResults["statuses"]:
                    ## update largestTweetId for next searches
                    if (int(tweet['id']) > self.largestTweetId):
                        self.largestTweetId = int(tweet['id'])
                    ## print
                    print ("pushing %s from @%s" %
                           (tweet['text'], tweet['user']['screen_name']))
                    ## send to all subscribers
                    self.sendToAllSubscribers(tweet['text'])
                    ## log onto local database
                    msgHashTags = []
                    for h in self.hashTags:
                        if(h in tweet['text']):
                            msgHashTags.append(h)
                    self.database.create(epoch=time(),
                                         dateTime=strftime("%Y/%m/%d %H:%M:%S", localtime()),
                                         text=tweet['text'].encode('utf-8'),
                                         receiver="twitter",
                                         hashTags=dumps(msgHashTags),
                                         prototypes=dumps(self.subscriberList),
                                         user=tweet['user']['screen_name'])
            self.lastTwitterCheck = time()

    ## end twitterReceiver
    def stop(self):
        pass

    ## authenticate to twitter using secrets
    def _authenticateTwitter(self):
        print "trying to authenticate to Twitter"
        try:
            self.mTwitter = Twython(app_key = self.secrets['CONSUMER_KEY'],
                                    app_secret = self.secrets['CONSUMER_SECRET'],
                                    oauth_token = self.secrets['ACCESS_TOKEN'],
                                    oauth_token_secret = self.secrets['ACCESS_SECRET'])
            self.twitterAuthenticated = True
        except:
            self.mTwitter = None
            self.twitterAuthenticated = False

    ## get largest Id for tweets in twitterResults
    def _getLargestTweetId(self):
        if (not self.twitterResults is None):
            for tweet in self.twitterResults["statuses"]:
                print ("Tweet %s from @%s at %s" %
                       (tweet['id'],
                        tweet['user']['screen_name'],
                        tweet['created_at']))
                print tweet['text'],"\n"
                if (int(tweet['id']) > self.largestTweetId):
                    self.largestTweetId = int(tweet['id'])

    ## query twitter
    def _searchTwitter(self):
        if(not self.twitterAuthenticated):
            self._authenticateTwitter()
        if ((self.twitterAuthenticated) and (not self.mTwitter is None)):
            try:
                self.twitterResults = self.mTwitter.search(q=" OR ".join(self.hashTags),
                                                           include_entities="false",
                                                           count="50",
                                                           result_type="recent",
                                                           since_id=self.largestTweetId)
            except:
                self.twitterAuthenticated = False
                self.twitterResults = None
        else:
            self.twitterResults = None
