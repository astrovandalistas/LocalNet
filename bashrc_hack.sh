## molaa
#cd /home/pi/Dev/Freenet
#python runDNS.py
sudo /etc/init.d/dnsmasq stop
isrun=`ps -u tgh | grep python | wc -l`
if [ $isrun -lt 1 ] 
then 
    cd /home/pi/Dev/LocalNet
    while [ 1 -le 20 ]
    do
	python localnet.py --inport=8900 --webserver=foocoop.mx --webserverport=3700 --inip=aeffect07.local &
	killpid=$!
	sleep 600
	kill -9 $killpid
    done
fi

