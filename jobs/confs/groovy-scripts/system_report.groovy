import java.text.SimpleDateFormat

def str_view = "00 Unstable Jobs (Production)"

def workspace = build.getEnvironment(listener).get('WORKSPACE')

def cur_date = new Date()

def sdf = new SimpleDateFormat("dd/MM/yyyy")

def date = sdf.format(cur_date)

def view = hudson.model.Hudson.instance.getView(str_view)

def view_url = view.getAbsoluteUrl()


f = new File("$workspace/exported-artifacts/upstream_report.html")

f.write("""<!DOCTYPE html><head><style type="text/css">
                 table.gridtable {
                     border-collapse: collapse;
                     table-layout:fixed;
                     width:1600px;
                     font-family: monospace;
                     font-size:13px;
                 }
                 .head {
                     font-size:20px;
                     font-family: arial;
                 }
                 .sub {
                     font-size:18px;
                     background-color:#e5e5e5;
                     font-family: arial;
                 }
                 pre {
                     font-family: monospace;
                     display: inline;
                     white-space: pre-wrap;
                     white-space: -moz-pre-wrap !important;
                     white-space: -pre-wrap;
                     white-space: -o-pre-wrap;
                     word-wrap: break-word;
                 }
             </style>
             </head>
             <body>
                 <table class="gridtable" border=2>
                     <tr><th colspan=2 class=head>
                         RHEVM CI Jenkins Daily Report - $date
                     </th></tr>""")

def name = view.name

f.append("""<tr><th colspan=2 class=sub>
                    <font color="blue"><a href="$view_url">$name</a></font>
                 </th></tr>""")
def job_name = ""
def job_url = ""
//copy all projects of a view
for(item in view.getAllItems())
{
  job_url = item.getAbsoluteUrl()
  println job_url
  println item.name
  def desc = item.getDescription()
  job_name = item.name
  println("Job name is: $item.name")
  if(desc != null && desc != "")
  {
    f.append("""
                     <tr><td>
                         <a href="$job_url">$job_name</a>
                     </td><td>
                         $desc
                     </td></tr>
                     """)
    println("Job desc is: $desc")
  }
  else
  {
      f.append("""
                     <tr><td>
                         <a href="$job_url">$job_name</a>
                     </td><td>
                         No Description
                     </td></tr>
                     """)
    println("No description")
  }
}
