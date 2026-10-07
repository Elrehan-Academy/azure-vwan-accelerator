targetScope = 'resourceGroup'

@description('Name of the Standard Virtual WAN.')
param virtualWanName string

@description('Location of the Virtual WAN resource.')
param virtualWanLocation string

@description('Hub configurations passed to the pinned Microsoft module.')
param hubs array

@description('Resource tags.')
param tags object = {}

module network 'br/public:avm/ptn/network/virtual-wan:0.2.0' = {
  name: 'network-${uniqueString(resourceGroup().id, virtualWanName)}'
  params: {
    virtualWanParameters: {
      virtualWanName: virtualWanName
      location: virtualWanLocation
      type: 'Standard'
    }
    virtualHubParameters: hubs
    tags: tags
    enableTelemetry: false
  }
}

output virtualWanResourceId string = network.outputs.resourceId
output virtualHubs array = network.outputs.virtualHubs
