## molaa
isrun=`ps -u tgh | grep python | wc -l`
if [ $isrun -lt 1 ] 
then 
    cd /home/pi/Dev/LocalNet
    rm -rf ./stop.sh
    while [ ! -f ./stop.sh ]
    do
	python localnet.py --inport=8900 --webserver=foocoop.mx --webserverport=3700 --inip=aeffect07.local &
	killpid=$!
	sleep 600
	kill -9 $killpid
    done
    rm -rf ./stop.sh
    sudo halt -n
fi
