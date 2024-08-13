from __future__ import division, absolute_import, unicode_literals

import re
import json
import urlparse
import socket

from scrapy.http import Request
from product_ranking.items import FortuneItem
from product_ranking.spiders import BaseProductsSpider, cond_set_value
from product_ranking.validation import BaseValidator

class fortune500ProductsSpider(BaseValidator, BaseProductsSpider):
    name = 'fortune500_products'
    allowed_domains = ["fortune.com", 'www.stock.walmart.com', 'www.exxonmobil.com', 'www.berkshirehathaway.com',
                       'www.apple.com', 'www.unitedhealthgroup.com', 'www.mckesson.com', 'www.cvshealth.com', 'www.amazon.com',
                       'www.att.com', 'www.gm.com', 'www.corporate.ford.com', 'www.amerisourcebergen.com', 'www.chevron.com',
                       'www.cardinalhealth.com', 'www.costco.com', 'www.verizon.com', 'www.thekrogerco.com', 'www.ge.com',
                       'www.walgreensbootsalliance.com', 'www.jpmorganchase.com', 'www.fanniemae.com', 'www.abc.xyz',
                       'www.homedepot.com', 'www.bankofamerica.com', 'www.express-scripts.com', 'www.wellsfargo.com',
                       'www.boeing.com', 'www.phillips66.com', 'www.antheminc.com', 'www.microsoft.com', 'www.valero.com',
                       'www.citigroup.com', 'www.comcastcorporation.com', 'www.ibm.com', 'www.delltechnologies.com',
                       'www.statefarm.com', 'www.jnj.com', 'www.freddiemac.com', 'www.target.com', 'www.lowes.com',
                       'www.marathonpetroleum.com', 'www.pg.com', 'www.metlife.com', 'www.ups.com', 'www.pepsico.com',
                       'www.intel.com', 'www.dow-dupont.com', 'www.adm.com', 'www.aetna.com', 'www.fedex.com',
                       'www.utc.com', 'www.prudential.com', 'www.albertsons.com', 'www.sysco.com', 'www.disney.com',
                       'www.humana.com', 'www.pfizer.com', 'www.hp.com', 'www.lockheedmartin.com', 'www.aig.com',
                       'www.centene.com', 'www.cisco.com', 'www.hcahealthcare.com', 'www.energytransfer.com',
                       'www.caterpillar.com', 'www.nationwide.com', 'www.morganstanley.com', 'www.libertymutual.com',
                       'www.newyorklife.com', 'www.gs.com', 'www.aa.com', 'www.bestbuy.com', 'www.cigna.com',
                       'www.charter.com', 'www.delta.com', 'www.facebook.com', 'www.honeywell.com', 'www.merck.com',
                       'www.allstate.com', 'www.tysonfoods.com', 'www.united.com', 'www.oracle.com', 'www.techdata.com',
                       'www.tiaa.org', 'www.tjx.com', 'www.americanexpress.com', 'www.coca-colacompany.com',
                       'www.publix.com', 'www.nike.com', 'www.andeavor.com', 'www.wfscorp.com', 'www.exeloncorp.com',
                       'www.massmutual.com', 'www.riteaid.com', 'www.conocophillips.com', 'www.chsinc.com',
                       'www.3m.com', 'www.timewarner.com', 'www.generaldynamics.com', 'www.usaa.com',
                       'www.capitalone.com', 'www.johndeere.com', 'www.intlfcstone.com', 'www.northwesternmutual.com',
                       'www.enterpriseproducts.com', 'www.travelers.com', 'www.hpe.com', 'www.pmi.com', 'www.21cf.com',
                       'www.abbvie.com', 'www.abbott.com', 'www.progressive.com', 'www.arrow.com',
                       'www.kraftheinzcompany.com', 'www.plainsallamerican.com', 'www.gilead.com',
                       'www.mondelezinternational.com', 'www.northropgrumman.com', 'www.raytheon.com',
                       'www.macysinc.com', 'www.usfoods.com', 'www.usbank.com', 'www.dollargeneral.com',
                       'www.internationalpaper.com', 'www.duke-energy.com', 'www.southerncompany.com', 'www.marriott.com', 'www.avnet.com',
                       'www.lilly.com', 'www.amgen.com', 'www.aboutmcdonalds.com', 'www.starbucks.com',
                       'www.qualcomm.com', 'www.dollartree.com', 'www.pbfenergy.com', 'www.ielp.com', 'www.aflac.com',
                       'www.autonation.com', 'www.penskeautomotive.com', 'www.whirlpoolcorp.com', 'www.up.com',
                       'www.southwest.com', 'www.manpowergroup.com', 'www.thermofisher.com', 'www.bms.com',
                       'www.halliburton.com', 'www.tenethealth.com', 'www.lear.com', 'www.cummins.com', 'www.micron.com',
                       'www.nucor.com', 'www.molinahealthcare.com', 'www.fluor.com', 'www.altria.com', 'www.paccar.com',
                       'www.thehartford.com', 'www.kohls.com', 'www.wdc.com', 'www.jabil.com', 'www.chs.net',
                       'www.visa.com', 'www.danaher.com', 'www.kimberly-clark.com', 'www.aecom.com', 'www.pnc.com',
                       'www.centurylink.com', 'www.nexteraenergy.com', 'www.pgecorp.com', 'www.synnex.com',
                       'www.wellcare.com', 'www.pfgc.com', 'www.searsholdings.com', 'www.synchronyfinancial.com',
                       'www.carmax.com', 'www.bnymellon.com', 'www.fcx.com', 'www.genpt.com', 'www.emerson.com',
                       'www.davita.com', 'www.supervalu.com', 'www.gapinc.com', 'www.generalmills.com',
                       'www.nordstrom.com', 'www.colgatepalmolive.com', 'www.aep.com', 'www.xpo.com',
                       'www.goodyear.com', 'www.omnicomgroup.com', 'www.cdw.com', 'www.sherwin.com', 'www.ppg.com',
                       'www.ti.com', 'www.chrobinson.com', 'www.westrock.com', 'www.cognizant.com',
                       'www.newellbrands.com', 'www.cbscorporation.com', 'www.evhc.net', 'www.monsanto.com',
                       'www.aramark.com', 'www.appliedmaterials.com', 'www.wm.com', 'www.dish.com', 'www.itw.com',
                       'www.lfg.com', 'www.hollyfrontier.com', 'www.cbre.com', 'www.textron.com', 'www.rossstores.com',
                       'www.principal.com', 'www.drhorton.com', 'www.mmc.com', 'www.devonenergy.com', 'www.aes.com',
                       'www.ecolab.com', 'www.landolakesinc.com', 'www.loews.com', 'www.kindermorgan.com',
                       'www.firstenergycorp.com', 'www.oxy.com', 'www.viacom.com', 'www.paypal.com',
                       'www.nglenergypartners.com', 'www.celgene.com', 'www.arconic.com', 'www.kelloggcompany.com',
                       'www.sands.com', 'www.stanleyblackanddecker.com', 'www.bookingholdings.com', 'www.lennar.com',
                       'www.lb.com', 'www.dteenergy.com', 'www.dominionenergy.com', 'www.rgare.com', 'www.jcpenney.com',
                       'www.mastercard.com', 'www.blackrock.com', 'www.henryschein.com', 'www.guardianlife.com',
                       'www.stryker.com', 'www.leucadia.com', 'www.vfc.com', 'www.adp.com', 'www.edisoninvestor.com',
                       'www.biogen.com', 'www.ussteel.com', 'www.core-mark.com', 'www.bedbathandbeyond.com',
                       'www.oneok.com', 'www.bbt.com', 'www.bd.com', 'www.ameriprise.com', 'www.farmers.com',
                       'www.firstdata.com', 'www.conedison.com', 'www.parker.com', 'www.anadarko.com',
                       'www.elcompanies.com', 'www.statestreet.com', 'www.tesla.com', 'www.netflix.com',
                       'www.alcoa.com', 'www.discover.com', 'www.praxair.com', 'www.csx.com', 'www.xcelenergy.com',
                       'www.unum.com', 'www.uhsinc.com', 'www.nrg.com', 'www.eogresources.com', 'www.sempra.com',
                       'www.toysrusinc.com', 'www.group1auto.com', 'www.entergy.com', 'www.molsoncoors.com',
                       'www.l3t.com', 'www.ball.com', 'www.autozone.com', 'www.murphyusa.com', 'www.mgmresorts.com',
                       'www.officedepot.com', 'www.huntsman.com', 'www.baxter.com', 'www.norfolksouthern.com',
                       'www.salesforce.com', 'www.labcorp.com', 'www.grainger.com', 'www.libertyinteractive.com',
                       'www.autoliv.com', 'www.livenationentertainment.com', 'www.xerox.com', 'www.leidos.com',
                       'www.corning.com', 'www.lithiainvestorrelations.com', 'www.expediagroup.com',
                       'www.republicservices.com', 'www.jacobs.com', 'www.sonicautomotive.com', 'www.ally.com',
                       'www.lkqcorp.com', 'www.fisglobal.com', 'www.pseg.com', 'www.bostonscientific.com', 'www.oreillyauto.com',
                       'www.aboutschwab.com', 'www.globalp.com', 'www.pvh.com', 'www.avisbudgetgroup.com',
                       'www.targaresources.com', 'www.hertz.com', 'www.calpine.com', 'www.mutualofomaha.com',
                       'www.crowncork.com', 'www.kiewit.com', 'www.dicks.com', 'www.pultegroupinc.com',
                       'www.navistar.com', 'www.thrivent.com', 'www.dcpmidstream.com', 'www.airproducts.com',
                       'www.veritivcorp.com', 'www.agcocorp.com', 'www.genworth.com', 'www.univar.com',
                       'www.newscorp.com', 'www.spartannash.com', 'www.westlake.com', 'www.williams.com',
                       'www.lamresearch.com', 'www.alaskaair.com', 'www.jll.com', 'www.anixter.com',
                       'www.campbellsoupcompany.com', 'www.interpublic.com', 'www.dovercorporation.com',
                       'www.zimmerbiomet.com', 'www.deanfoods.com', 'www.footlocker-inc.com', 'www.eversource.com',
                       'www.alliancedata.com', 'www.53.com', 'www.questdiagnostics.com', 'www.emcorgroup.com',
                       'www.wrberkley.com', 'www.wesco.com', 'www.coty.com', 'www.wecenergygroup.com', 'www.masco.com',
                       'www.dxc.technology', 'www.auto-owners.com', 'www.edwardjones.com', 'www.libertymedia.com',
                       'www.erieinsurance.com', 'www.thehersheycompany.com', 'www.pplweb.com',
                       'www.huntingtoningalls.com', 'www.mosaicco.com', 'www.jmsmucker.com', 'www.delekus.com',
                       'www.newmont.com', 'www.cbrands.com', 'www.ryder.com', 'www.nov.com', 'www.adobe.com',
                       'www.lifepointhealth.net', 'www.tractorsupply.com', 'www.thorindustries.com', 'www.dana.com',
                       'www.weyerhaeuser.com', 'www.jbhunt.com', 'www.darden.com', 'ir.yumchina.com',
                       'www.blackstone.com', 'www.berryglobal.com', 'www.bldr.com', 'www.activisionblizzard.com',
                       'www.jetblue.com', 'www.amphenol.com', 'www.amark.com', 'www.spiritaero.com',
                       'www.rrdonnelley.com', 'www.harris.com', 'www.expeditors.com', 'www.discovery.com',
                       'www.o-i.com', 'www.sanmina.com', 'www.key.com', 'www.afginc.com', 'www.oshkoshcorporation.com',
                       'www.rockwellcollins.com', 'www.kindredhealthcare.com', 'www.insight.com',
                       'www.drpeppersnapplegroup.com', 'www.americantower.com', 'www.fortive.com',
                       'www.ralphlauren.com', 'www.hrggroup.com', 'www.ascenaretail.com', 'www.unitedrentals.com',
                       'www.caseys.com', 'www.graybar.com', 'www.averydennison.com', 'www.mastec.com',
                       'www.cmsenergy.com', 'www.hdsupply.com', 'www.raymondjames.com', 'www.ncr.com', 'www.hanes.com',
                       'www.asburyauto.com', 'www.citizensbank.com', 'www.packagingcorp.com', 'www.alleghany.com',
                       'www.apachecorp.com', 'www.dillards.com', 'www.assurant.com', 'www.franklinresources.com',
                       'www.owenscorning.com', 'www.motorolasolutions.com', 'www.nvrinc.com',
                       'www.rockwellautomation.com', 'www.treehousefoods.com', 'www.wynnresorts.com', 'www.olin.com',
                       'www.aam.com', 'www.oldrepublic.com', 'www.chemours.com', 'www.iheartmedia.com',
                       'www.ameren.com', 'www.ajg.com', 'www.celanese.com', 'www.sealedair.com', 'www.ugicorp.com',
                       'www.realogy.com', 'www.burlington.com', 'www.regions.com', 'www.aksteel.com',
                       'www.securian.com', 'www.spglobal.com', 'www.markelcorp.com', 'www.ta-petro.com',
                       'www.conduent.com', 'www.mtb.com', 'www.thecloroxcompany.com', 'www.amtrustfinancial.com',
                       'www.kkr.com', 'www.ulta.com', 'www.yum.com', 'www.regeneron.com', 'www.windstream.com',
                       'www.magellanhealth.com', 'www.westernsouthern.com', 'www.theice.com', 'www.ingredion.com',
                       'www.wyndhamworldwide.com', 'www.tollbrothers.com', 'www.seaboardcorp.com', 'www.boozallen.com',
                       'www.firstam.com', 'www.cinfin.com', 'www.avoninvestor.com', 'www.northerntrust.com',
                       'www.fiserv.com', 'www.harley-davidson.com', 'www.cheniere.com', 'www.pattersoncompanies.com',
                       'www.peabodyenergy.com', 'www.onsemi.com', 'www.simon.com', 'www.westernunion.com',
                       'www.netapp.com', 'www.polaris.com', 'www.pxd.com', 'www.abm.com', 'www.vistraenergy.com',
                       'www.cintas.com', 'www.hess.com', 'www.hosthotels.com', 'www.kellyservices.com',
                       'www.genesishcc.com', 'www.michaels.com', 'www.amd.com', 'www.zoetis.com',
                       'www.williams-sonomainc.com', 'www.fbhs.com', 'www.biglots.com', 'www.roberthalf.com',
                       'www.postholdings.com', 'www.hasbro.com', 'www.hanover.com', 'www.navient.com', 'www.intuit.com',
                       'www.domtar.com', 'www.marathonoil.com', 'www.cerner.com', 'www.analog.com', 'www.tdsinc.com',
                       'www.essendant.com', 'www.sonoco.com', 'www.juniper.net', 'www.cmc.com', 'www.csra.com',
                       'www.uabiz.com', 'www.rpminc.com', 'www.tsys.com', 'www.levistrauss.com', 'www.brunswick.com',
                       'www.yrcw.com', 'www.mattel.com', 'www.fmglobal.com', 'www.nisource.com', 'www.caesars.com',
                       'www.ea.com', 'www.dynegy.com', 'www.mccormickcorporation.com', 'www.troweprice.com',
                       'www.orbitalatk.com', 'www.tutorperini.com', 'www.brookdale.com', 'www.huntington.com',
                       'www.wayfair.com', 'www.rushenterprises.com', 'www.xyleminc.com', 'www.neimanmarcusgroup.com',
                       'www.hyatt.com', 'www.sprouts.com', 'www.dieboldnixdorf.com', 'www.ropertech.com',
                       'www.smartandfinal.com', 'www.commscope.com', 'www.tapestry.com', 'www.diplomatpharmacy.com',
                       'www.chipotle.com', 'www.agilent.com', 'www.saic.com', 'www.mdu.com',
                       'www.selectmedicalholdings.com', 'www.bc.com', 'www.nationalgeneral.com', 'www.scana.com',
                       'www.graphicpkg.com', 'www.fastenal.com', 'www.schneider.com', 'www.laureate.net',
                       'www.becn.com', 'www.kbhome.com', 'www.equinix.com', 'www.terex.com', 'www.crowncastle.com',
                       'www.caci.com', 'www.watsco.com', 'www.cokeconsolidated.com', 'www.welltower.com', 'www.adt.com',
                       'www.ametek.com', 'www.cnoinc.com', 'www.campingworld.com', 'www.lpl.com', 'www.nblenergy.com',
                       'www.bloominbrands.com', 'www.moodys.com', 'www.symantec.com', 'www.amkor.com', 'www.skx.com',
                       'www.kbr.com', 'www.tiffany.com', 'www.torchmarkcorp.com', 'www.broadridge.com', 'www.qg.com',
                       'www.cfindustries.com', 'www.carlisle.com', 'www.silganholdings.com', 'www.bemis.com',
                       'www.ca.com', 'www.hubgroup.com', 'www.worldpay.com', 'www.ingles-markets.com', 'www.snapon.com',
                       'www.dentsplysirona.com', 'www.calumetspecialty.com', 'www.globalpaymentsinc.com',
                       'www.encompasshealth.com', 'www.martinmarietta.com', 'www.business.nasdaq.com',
                       'www.leggett.com', 'www.ufpi.com', 'www.sallybeautyholdings.com', 'www.flowersfoods.com',
                       'www.barnesandnobleinc.com', 'www.american-equity.com', 'www.vulcanmaterials.com',
                       'www.taylormorrison.com', 'www.wabtec.com', 'www.crestwoodlp.com', 'www.ironmountain.com',
                       'www.lennoxinternational.com', 'www.generalcable.com', 'www.ae.com', 'www.churchdwight.com',
                       'www.platformspecialtyproducts.com', 'www.jeld-wen.com', 'www.onemainfinancial.com',
                       'www.colfaxcorp.com', 'www.zebra.com', 'www.andersonsinc.com', 'www.amtd.com', 'www.carlyle.com',
                       'www.hubbell.com', 'www.trin.net', 'www.darlingii.com', 'www.flowserve.com',
                       'www.anteroresources.com', 'www.skyworksinc.com', 'www.landstar.com', 'www.buckeye.com',
                       'www.mrcglobal.com', 'www.cmegroup.com', 'www.greif.com', 'www.nexeosolutions.com',
                       'www.cooperstandard.com', 'www.urbn.com', 'www.lsccom.com', 'www.sabre.com', 'www.gpreinc.com',
                       'www.hexion.com', 'www.stericycle.com', 'www.wmg.com', 'www.ventasreit.com',
                       'www.scansource.com', 'www.pinnaclewest.com', 'www.alexion.com', 'www.pb.com', 'www.cit.com',
                       'www.countryfinancial.com', 'www.cunamutual.com', 'www.triumphgroup.com', 'www.transdigm.com',
                       'www.atimetals.com', 'www.resolutefp.com', 'www.acuitybrands.com', 'www.abercrombie.com',
                       'www.kla-tencor.com', 'www.weismarkets.com', 'www.pugetenergy.com', 'www.mednax.com',
                       'www.karauctionservices.com', 'www.polyone.com', 'www.fmc.com', 'www.edwards.com',
                       'www.microchip.com', 'www.amerco.com', 'www.mercuryinsurance.com', 'www.americannational.com',
                       'www.carters.com', 'www.iff.com', 'www.aarons.com', 'www.alliantenergy.com', 'www.eqt.com',
                       'www.monsterbevcorp.com', 'www.buildwithbmc.com', 'www.ryerson.com', 'www.equifax.com',
                       'www.regalbeloit.com', 'www.odfl.com', 'www.amwater.com', 'www.bgcpartners.com',
                       'www.brinks.com', 'www.meritor.com', 'www.sentry.com', 'www.sandersonfarms.com',
                       'www.kapstonepaper.com', 'www.gartner.com', 'www.iac.com', 'www.tailoredbrands.com',
                       'www.wabco-auto.com', 'www.insperity.com', 'www.comerica.com', 'www.trinet.com', 'www.avaya.com',
                       'www.ashland.com', 'www.meritagehomes.com', 'www.skywest.com', 'www.usg.com', 'www.swn.com',
                       'www.keysight.com', 'www.cineworldplc.com', 'www.mutualofamerica.com', 'www.paychex.com',
                       'www.brinker.com', 'www.pngaming.com', 'www.gannett.com', 'www.visteon.com',
                       'www.pinnaclefoods.com', 'www.intuitivesurgical.com', 'www.clr.com', 'www.sci-corp.com',
                       'www.scientificgames.com', 'www.albemarle.com', 'www.atmosenergy.com', 'www.hologic.com',
                       'www.hrblock.com', 'www.qorvo.com', 'www.steelcase.com', 'corporate.univision.com',
                       'www.worthingtonindustries.com', 'www.timken.com', 'www.aosmith.com', 'www.pricesmart.com',
                       'www.stifel.com', 'www.brown-forman.com', 'www.cinemark.com', 'www.graniteconstruction.com',
                       'www.dycomind.com', 'www.cleanharbors.com', 'www.firstsolar.com', 'www.scotts.com',
                       'www.crackerbarrel.com', 'www.triplesmanagement.com', 'www.firstrepublic.com',
                       'www.servicemaster.com', 'www.connection.com', 'www.genesco.com', 'www.medmutual.com',
                       'www.mscdirect.com', 'www.leggmason.com', 'www.hyster-yale.com', 'www.agm.com', 'www.citrix.com',
                       'www.acadiahealthcare.com', 'www.varian.com', 'www.groupon.com', 'www.aleris.com',
                       'www.spragueenergy.com', 'www.coopertire.com', 'www.hain.com', 'www.pennmutual.com',
                       'www.clns.com', 'www.arcb.com', 'www.presidio.com', 'www.tripointegroup.com', 'www.annaly.com',
                       'www.giii.com', 'www.amcnetworks.com', 'www.enablemidstream.com', 'www.ciena.com',
                       'www.dswinc.com', 'www.convergys.com', 'www.pkhotelsandresorts.com', 'www.poolcorp.com',
                       'www.fossilgroup.com', 'www.dominos.com', 'www.craneco.com', 'www.caleres.com',
                       'www.tempursealy.com', 'www.tetratech.com', 'www.illumina.com', 'www.valmont.com',
                       'www.hill-rom.com', 'www.unisys.com', 'www.zionsbancorporation.com', 'www.sbgi.net',
                       'www.lpcorp.com', 'www.mt.com', 'www.synopsys.com', 'www.kemper.com', 'www.cabotcorp.com',
                       'www.evergyinc.com', 'www.rentacenter.com', 'www.hawaiianairlines.com', 'www.revloninc.com',
                       'www.syneoshealth.com', 'www.publicstorage.com', 'www.ttm.com', 'www.vectren.com',
                       'www.trimble.com', 'www.distributionnow.com', 'www.spirit.com', 'www.asgn.com',
                       'www.lincolnelectric.com', 'www.prologis.com', 'www.rangeresources.com', 'www.teledyne.com',
                       'www.vishay.com', 'www.bostonproperties.com', 'www.applied.com', 'www.ghco.com', 'www.amica.com',
                       'www.concho.com', 'www.itt.com', 'www.kcsouthern.com', 'www.mdcholdings.com',
                       'www.westarenergy.com', 'www.pnk.com', 'www.hei.com', 'www.tegna.com', 'www.swgasholdings.com',
                       'www.vistaoutdoor.com', 'www.bonton.com', 'www.supermicro.com', 'www.plexus.com',
                       'www.trueblue.com', 'www.magellanlp.com', 'www.thetorocompany.com', 'www.akamai.com',
                       'www.moog.com', 'www.vrtx.com', 'www.equityapartments.com', 'www.selective.com', 'www.aptar.com',
                       'www.bench.com', 'www.columbia.com', 'www.aschulman.com', 'www.versoco.com',
                       'www.digitalrealty.com', 'www.gnc.com', 'www.etrade.com', 'www.khov.com', 'www.maximus.com',
                       'www.twitter.com', 'www.parpacific.com', 'www.parexel.com', 'www.rh.com', 'www.nexstar.tv',
                       'www.knight-swift.com', 'www.redhat.com', 'www.belden.com', 'www.boydgaming.com',
                       'www.primoriscorp.com', 'www.gardnerdenver.com', 'www.donaldson.com', 'www.partycity.com',
                       'www.jcrew.com', 'www.enersys.com', 'www.guess.com', 'www.patenergy.com', 'www.wglholdings.com',
                       'www.wolverineworldwide.com', 'www.xilinx.com', 'www.vno.com', 'www.middleby.com',
                       'www.momentive.com', 'www.clevelandcliffs.com', 'www.ggp.com', 'www.cypress.com',
                       'www.archcoal.com', 'www.gms.com', 'www.waters.com', 'www.hbfuller.com', 'www.amg.com',
                       'www.perkinelmer.com', 'www.edgewell.com', 'www.maximintegrated.com', 'www.kofc.org',
                       'www.idexcorp.com', 'www.dstsystems.com', 'www.chicosfas.com', 'www.nuskinenterprises.com',
                       'www.hermanmiller.com', 'www.nationallifegroup.com', 'www.curtisswright.com',
                       'www.njresources.com', 'www.revgroup.com', 'www.muellerindustries.com', 'www.geogroup.com',
                       'www.allisontransmission.com', 'www.oge.com', 'www.thecheesecakefactory.com', 'www.prahs.com',
                       'www.tupperwarebrands.com', 'www.euronetworldwide.com', 'www.fleetcor.com',
                       'www.nationstarholdings.com', 'www.godaddy.com', 'www.blackhawknetwork.com', 'www.cboe.com',
                       'www.snyderslance.com', 'www.murphyoilcorp.com', 'www.cdkglobal.com', 'www.texasroadhouse.com',
                       'www.kirbycorp.com', 'www.squareup.com', 'www.gwrr.com', 'www.zayo.com', 'www.newmarket.com',
                       'www.99only.com', 'www.pcm.com', 'www.federatedinsurance.com', 'www.hnicorp.com',
                       'www.hptreit.com', 'www.gbrx.com', 'www.bio-rad.com', 'www.avalonbay.com', 'www.regi.com',
                       'www.atlasair.com', 'www.teradata.com', 'www.lci1.com', 'www.teleflex.com', 'www.verisk.com',
                       'www.popular.com', 'www.workday.com', 'www.coopercos.com', 'www.express.com', 'www.teradyne.com',
                       'www.werner.com', 'www.oaktreecapital.com', 'www.woodward.com', 'www.f5.com',
                       'www.valvoline.com', 'www.rrts.com', 'www.semgroupcorp.com', 'www.catalent.com',
                       'www.quorumhealth.com', 'www.universalcorp.com', 'www.nordson.com', 'www.resmed.com',
                       'www.towerinternational.com', 'www.fredsinc.com', 'www.fbmsales.com', 'www.kennametal.com',
                       'www.autodesk.com', 'www.plygem.com', 'www.central.com', 'www.matson.com', 'www.echostar.com',
                       'www.genesisenergy.com', 'www.svb.com', 'www.itron.com', 'www.portlandgeneral.com',
                       'www.crc.com', 'www.esterline.com', 'www.dyn-intl.com', 'www.amnhealthcare.com',
                       'www.griffon.com', 'www.valhi.net', 'www.hexcel.com', 'www.idexx.com', 'www.deluxe.com',
                       'www.mihomes.com', 'www.kraton.com', 'www.stewart.com', 'www.marriottvacationsworldwide.com',
                       'www.spxflow.com', 'www.accobrands.com', 'www.echo.com', 'www.cadence.com', 'www.nuance.com',
                       'www.finishline.com', 'www.transunion.com', 'www.servicenow.com', 'www.summit-materials.com',
                       'www.engilitycorp.com', 'www.ferrellgas.com', 'www.interactivebrokers.com', 'www.stepan.com',
                       'www.oceaneering.com', 'www.cimarex.com', 'www.rexnord.com', 'www.beazer.com', 'www.mksinst.com',
                       'www.vailresorts.com', 'www.ohionational.com', 'www.topbuild.com', 'www.bbinsurance.com',
                       'www.aerojetrocketdyne.com', 'www.bned.com', 'www.superiorenergy.com', 'www.verifone.com',
                       'www.childrensplace.com', 'www.tribunemedia.com', 'www.hcsg.com', 'www.siteone.com',
                       'www.criver.com', 'www.corelogic.com', 'www.ensigngroup.net', 'www.hcpi.com',
                       'www.borgwarner.com', 'www.fnf.com', 'www.suntrust.com', 'www.iqvia.com', 'www.rsac.com',
                       'www.nvidia.com', 'www.voya.com', 'www.centerpointenergy.com', 'www.ebay.com', 'www.eastman.com',
                       'www.amfam.com', 'www.steeldynamics.com', 'www.pacificlife.com', 'www.chk.com',
                       'www.mohawkind.com', 'www.quantaservices.com', 'www.advanceautoparts.com', 'www.owens-minor.com',
                       'www.unfi.com', 'www.tenneco.com', 'www.conagrabrands.com', 'www.gamestop.com',
                       'www.hormelfoods.com', 'www.hiltonworldwide.com', 'www.frontier.com'
                       ]

    FORTUNE_API = 'http://fortune.com/api/v2/list/2358051/expand/item/ranking/asc/0/25'

    def __init__(self, sort_mode=None, *args, **kwargs):
        super(fortune500ProductsSpider, self).__init__(
            site_name=self.allowed_domains[0],
            *args, **kwargs)
        socket.setdefaulttimeout(60)

    def start_requests(self):
        yield Request(
            url=self.FORTUNE_API,
            callback=self._parse_single_product
        )

    def _parse_single_product(self, response):
        return self.parse_product(response)

    def parse_product(self, response):
        product = FortuneItem()
        data = json.loads(response.body)
        items = data.get('list-items')
        for item in items:
            company_name = item.get('meta', {}).get('fullname').strip()
            company_url = item.get('meta', {}).get('website')
            yield Request(
                url=company_url,
                meta={'product': product,
                      'company_name': company_name,
                      'company_url': company_url
                      },
                callback=self.parse_hubspot_data
            )
        yield product

    def parse_hubspot_data(self, response):
        product = response.meta.get('product')
        company_name = response.meta.get('company_name')
        company_url = response.meta.get('company_url')

        product['company_name'] = None
        product['url'] = None
        product['account_name'] = None

        account_name = None
        hubspot_loader = response.xpath("//script[@id='hs-script-loader']/@src").extract()
        if hubspot_loader:
            account_name = hubspot_loader[0].split('/')[-1].split('.')[0]

        cond_set_value(product, 'company_name', company_name)
        cond_set_value(product, 'url', company_url)
        cond_set_value(product, 'account_name', account_name)

        return product

    def _scrape_total_matches(self, response):
        total_match = response.xpath(
            "//*[@data-total-products]/@data-total-products").extract()

        return int(total_match[0]) if total_match else 0

    def _scrape_product_links(self, response):
        # self.product_links = list(set(response.xpath("//div[@class='product-container']//a/@href").extract()))
        #
        # for item_url in self.product_links:
        url = response.meta.get('url')
        req = Request(
            url=url,
            callback=self.parse_product,
            dont_filter=True
        )
        yield req, FortuneItem()

    def _scrape_next_results_page_link(self, response):
        if not self.product_links:
            return
        next_page_link = response.xpath("//li[@class='next']//a/@href").extract()
        if next_page_link:
            return urlparse.urljoin(response.url, next_page_link[0])

    def _clean_text(self, text):
        return re.sub("[\n\t\r]", "", text).strip()
