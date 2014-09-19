'use strict';

angular.module('txiRushApp')
  .controller('requestController', ['$scope', '$rootScope', '$http', function($scope, $rootScope, $http) {
        $scope.pageName = "Pick Me Up";
        $rootScope.requesting=true;
        $scope.selectedLocation = 'None';

        $http.get($rootScope.serve("routes")).success(function(data){
            var east = data.routes[1].locations;
            var west = data.routes[0].locations;
            $scope.locations = east.splice(0,10).concat(west.splice(8,1));
        });
        
        /**
         * 
         * @param {int} num van number, 1 or 2
         * @param {bool} first true if the dot is the first dot
         * @param {bool} last true if the dot is the last dot
         * @param {String} loc location of van
         * @returns {String} image string of correct dot to use
         */
        $scope.dot = function(first, last, loc){
            if ($scope.selectedLocation===loc){
                if (first){
                    return 'img/dots/closedDotTop.png';
                }
                else if (last){
                    return 'img/dots/closedDotBottom.png';
                }
                else{
                    return 'img/dots/closedDot.png';
                }
            }
            else{
                if (first){
                    return 'img/dots/openDotTop.png';
                }
                else if (last){
                    return 'img/dots/openDotBottom.png';
                }
                else{
                    return 'img/dots/openDot.png';
                }
            }
        };
        
        $scope.select = function(location){
            $scope.selectedLocation=location;
        };
        
        $scope.submitable = function(){
            if ($scope.selectedLocation!=='None'){
                return true;
            }
            else{
                return false;
            }
        };

        $scope.submitRequest = function(){
            var postRequest = "https://rushtxi.mit.edu/app/api/pickup/"
                +$scope.selectedLocation;

            $http.post(postRequest).success(function(data){
                alert("we'll send a van right away!");
            });
            $rootScope.requesting=false;
        }
  }]);