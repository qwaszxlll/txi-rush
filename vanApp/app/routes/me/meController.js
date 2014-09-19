'use strict';

angular.module('txiRushApp')
  .controller('meController', ['$scope', '$rootScope', '$http','$interval', '$location',
    function($scope, $rootScope, $http, $interval, $location) {
        $scope.pageName = "Me";

        $scope.saveMe = function(){
            $scope.meData = {
                "name" : $rootScope.me.name,
                "cell" : $rootScope.me.cell
            }
            $http.post($rootScope.serve("rushee"), $scope.meData).success(function(data){
                alert("Your information has been saved");
                $scope.$location.path("/events");
            });
        }
  }]);