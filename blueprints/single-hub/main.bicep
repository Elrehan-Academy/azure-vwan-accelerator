targetScope = 'resourceGroup'

@description('Name of the Standard Virtual WAN.')
@minLength(1)
param virtualWanName string

@description('Location of the Virtual WAN resource.')
param virtualWanLocation string = resourceGroup().location

@description('Name of the virtual hub.')
@minLength(1)
param hubName string

@description('Azure region for the hub.')
param hubLocation string = resourceGroup().location

@description('Hub IPv4 CIDR. Must not overlap connected networks; /24 or larger.')
param hubAddressPrefix string

@description('Resource tags such as owner, environment, and cost centre.')
param tags object = {}

module network '../../modules/network.bicep' = {
  name: 'single-hub-network'
  params: {
    virtualWanName: virtualWanName
    virtualWanLocation: virtualWanLocation
    hubs: [
      {
        hubName: hubName
        hubLocation: hubLocation
        hubAddressPrefix: hubAddressPrefix
        secureHubParameters: {
          deploySecureHub: false
        }
        expressRouteParameters: {
          deployExpressRouteGateway: false
        }
        s2sVpnParameters: {
          deployS2SVpnGateway: false
        }
        p2sVpnParameters: {
          deployP2SVpnGateway: false
        }
      }
    ]
    tags: tags
  }
}

output virtualWanResourceId string = network.outputs.virtualWanResourceId
output virtualHubs array = network.outputs.virtualHubs
